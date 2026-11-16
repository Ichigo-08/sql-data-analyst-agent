
import sqlite3
import random
from pathlib import Path
from datetime import date, timedelta

# Database location
DB_PATH = Path(__file__).parent / "data" / "sample.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

random.seed(42)

conn = sqlite3.connect(DB_PATH)
conn.execute("PRAGMA foreign_keys = ON")
cur = conn.cursor()

# Remove previous sample tables if they exist
cur.executescript("""
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;
""")

# 1. CREATE TABLES
cur.executescript("""
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    city TEXT,
    region TEXT,
    signup_date TEXT,
    customer_segment TEXT
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT,
    subcategory TEXT,
    unit_price REAL,
    stock_quantity INTEGER,
    supplier TEXT
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT,
    status TEXT,
    payment_method TEXT,
    shipping_city TEXT,
    shipping_region TEXT,
    total_amount REAL,
    FOREIGN KEY(customer_id)
        REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER,
    unit_price REAL,
    discount_percent REAL,
    line_total REAL,
    FOREIGN KEY(order_id) REFERENCES orders(order_id),
    FOREIGN KEY(product_id) REFERENCES products(product_id),
    UNIQUE(order_id, product_id)
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_orders_date ON orders(order_date);
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
""")

# 2. GENERATE CUSTOMERS
first_names = [
    "Aarav", "Aditi", "Arjun", "Ananya", "Rahul",
    "Priya", "Rohan", "Meera", "Kiran", "Neha",
    "Ishaan", "Kavya", "Dev", "Diya", "Kabir"
]

last_names = [
    "Sharma", "Patel", "Reddy", "Nair", "Iyer",
    "Mehta", "Gupta", "Rao", "Khan", "Das"
]

cities = {
    "South": ["Bengaluru", "Chennai", "Hyderabad", "Kochi"],
    "North": ["Delhi", "Jaipur", "Lucknow", "Noida"],
    "West": ["Mumbai", "Pune", "Ahmedabad", "Surat"],
    "East": ["Kolkata", "Patna", "Guwahati", "Ranchi"],
    "Central": ["Bhopal", "Indore", "Raipur"]
}

segments = ["Consumer", "Corporate", "Small Business"]

customers = []

for i in range(1, 1001):
    first = random.choice(first_names)
    last = random.choice(last_names)
    region = random.choice(list(cities))
    city = random.choice(cities[region])

    signup = date(2021, 1, 1) + timedelta(
        days=random.randint(0, 2100)
    )

    customers.append((
        i, first, last,
        f"{first.lower()}.{last.lower()}.{i}@example.com",
        city, region, signup.isoformat(),
        random.choice(segments)
    ))

cur.executemany("""
INSERT INTO customers VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", customers)

# 3. GENERATE PRODUCTS
categories = {
    "Electronics": ["Mobiles", "Computers", "Accessories"],
    "Fashion": ["Men", "Women", "Footwear"],
    "Home": ["Furniture", "Kitchen", "Decor"],
    "Beauty": ["Skincare", "Makeup", "Haircare"],
    "Sports": ["Fitness", "Outdoor", "Cycling"],
    "Books": ["Business", "Technology", "Fiction"]
}

products = []

for i in range(1, 201):
    category = random.choice(list(categories))

    products.append((
        i,
        f"Product {i:03d}",
        category,
        random.choice(categories[category]),
        round(random.uniform(149, 49999), 2),
        random.randint(0, 500),
        f"Supplier {random.randint(1, 35):02d}"
    ))

cur.executemany("""
INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)
""", products)

# 4. GENERATE ORDERS AND ORDER ITEMS
statuses = [
    "Delivered", "Shipped", "Processing",
    "Cancelled", "Returned"
]

status_weights = [69, 12, 10, 6, 3]

payments = [
    "UPI", "Credit Card", "Debit Card",
    "Net Banking", "Cash on Delivery"
]

orders = []
items = []
item_id = 1

for order_id in range(1, 5001):

    customer_id = random.randint(1, 1000)
    customer = customers[customer_id - 1]

    order_date = date(2024, 1, 1) + timedelta(
        days=random.randint(0, 1045)
    )

    status = random.choices(
        statuses, weights=status_weights
    )[0]

    payment = random.choice(payments)

    item_count = random.choices(
        [1, 2, 3, 4, 5],
        weights=[12, 30, 30, 20, 8]
    )[0]

    selected_products = random.sample(range(1, 201), item_count)
    total = 0

    for product_id in selected_products:

        product = products[product_id - 1]
        quantity = random.randint(1, 5)
        price = product[4]
        discount = random.choice([0, 5, 10, 15, 20])

        line_total = round(
            quantity * price * (1 - discount / 100), 2
        )

        total += line_total

        items.append((
            item_id, order_id, product_id,
            quantity, price, discount, line_total
        ))

        item_id += 1

    orders.append((
        order_id,
        customer_id,
        order_date.isoformat(),
        status,
        payment,
        customer[4],
        customer[5],
        round(total, 2)
    ))

cur.executemany("""
INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", orders)

cur.executemany("""
INSERT INTO order_items VALUES (?, ?, ?, ?, ?, ?, ?)
""", items)

# 5. VERIFY DATABASE
conn.commit()

print("\nDATABASE CREATED SUCCESSFULLY")
print("--------------------------------")

for table in ["customers", "products", "orders", "order_items"]:
    count = cur.execute(
        f"SELECT COUNT(*) FROM {table}"
    ).fetchone()[0]

    print(f"{table}: {count:,} records")

violations = cur.execute(
    "PRAGMA foreign_key_check"
).fetchall()

print("\nForeign key check:",
      "PASS" if not violations else violations)

print("\nDatabase location:", DB_PATH)

conn.close()
