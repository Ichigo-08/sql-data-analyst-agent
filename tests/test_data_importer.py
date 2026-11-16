import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect, text

from database.data_importer import (
    DataImportError,
    import_dataframe,
    read_uploaded_dataframe,
    validate_table_name,
)


@pytest.fixture
def engine(tmp_path):
    db = tmp_path / "import_test.db"
    engine = create_engine(f"sqlite:///{db}")
    yield engine
    engine.dispose()


def test_validate_table_name():
    assert validate_table_name("monthly_sales_2026") == "monthly_sales_2026"
    for invalid in ["", "1table", "table-name", "table name", "x; DROP TABLE users"]:
        with pytest.raises(DataImportError):
            validate_table_name(invalid)


def test_read_csv_upload():
    frame = read_uploaded_dataframe("sample.csv", b"id,name\n1,A\n2,B\n")
    assert list(frame.columns) == ["id", "name"]
    assert len(frame) == 2


def test_read_upload_rejects_bad_extension_and_empty_file():
    with pytest.raises(DataImportError):
        read_uploaded_dataframe("data.txt", b"a\n1")
    with pytest.raises(DataImportError):
        read_uploaded_dataframe("data.csv", b"")


def test_read_upload_rejects_duplicate_headers():
    with pytest.raises(DataImportError, match="unique"):
        read_uploaded_dataframe("dupes.csv", b"Name,name\nA,B\n")


def test_import_creates_table_and_preserves_values(engine):
    frame = pd.DataFrame({"id": [1, 2], "region": ["South", "West"], "amount": [10.5, 20.0]})
    result = import_dataframe(engine, frame, "new_orders")
    assert result == {"table_name": "new_orders", "imported_rows": 2, "total_rows": 2}
    assert inspect(engine).has_table("new_orders")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT SUM(amount) FROM new_orders")).scalar_one() == 30.5


def test_existing_table_fails_by_default(engine):
    import_dataframe(engine, pd.DataFrame({"id": [1]}), "records")
    with pytest.raises(DataImportError, match="already exists"):
        import_dataframe(engine, pd.DataFrame({"id": [2]}), "records")


def test_append_requires_matching_columns_and_appends(engine):
    import_dataframe(engine, pd.DataFrame({"id": [1], "name": ["A"]}), "records")
    with pytest.raises(DataImportError, match="columns to match"):
        import_dataframe(engine, pd.DataFrame({"id": [2], "other": ["B"]}), "records", if_exists="append")
    result = import_dataframe(engine, pd.DataFrame({"id": [2], "name": ["B"]}), "records", if_exists="append")
    assert result["imported_rows"] == 1
    assert result["total_rows"] == 2


def test_replace_requires_confirmation_and_replaces(engine):
    import_dataframe(engine, pd.DataFrame({"id": [1, 2]}), "records")
    with pytest.raises(DataImportError, match="Confirm replacement"):
        import_dataframe(engine, pd.DataFrame({"id": [3]}), "records", if_exists="replace")
    result = import_dataframe(
        engine, pd.DataFrame({"id": [3]}), "records", if_exists="replace", confirm_replace=True
    )
    assert result["total_rows"] == 1
    with engine.connect() as connection:
        assert connection.execute(text("SELECT id FROM records")).scalars().all() == [3]


def test_import_rejects_empty_frame_and_invalid_columns(engine):
    with pytest.raises(DataImportError):
        import_dataframe(engine, pd.DataFrame(), "records")
    frame = pd.DataFrame([[1, 2]], columns=["x", "x"])
    with pytest.raises(DataImportError, match="unique"):
        import_dataframe(engine, frame, "records")


def test_read_excel_upload_and_select_sheet():
    from io import BytesIO

    payload = BytesIO()
    with pd.ExcelWriter(payload, engine="openpyxl") as writer:
        pd.DataFrame({"id": [1], "value": ["first"]}).to_excel(writer, sheet_name="First", index=False)
        pd.DataFrame({"id": [2], "value": ["second"]}).to_excel(writer, sheet_name="Second", index=False)
    raw = payload.getvalue()
    frame = read_uploaded_dataframe("workbook.xlsx", raw, sheet_name="Second")
    assert frame.iloc[0]["value"] == "second"
