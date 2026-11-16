
from config.gemini_config import get_gemini_client

client = get_gemini_client()

print("Checking available Gemini models...\n")

for model in client.models.list():
    name = model.name or ""
    if "flash" in name.lower():
        print(name)
