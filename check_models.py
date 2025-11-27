import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)

print("Доступные модели для генерации контента:")
print("=" * 60)
for model in client.models.list():
    print(f"✅ {model.name}")
print("=" * 60)