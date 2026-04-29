import os
os.environ["GEMINI_API_KEY"] = "AIzaSyDuoFeimI1Gkg-_i58L5FquQdFXopzlpi4"
from google import genai
from google.genai import types

client = genai.Client()
try:
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Hello",
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )
    print("Success:", response.text)
except Exception as e:
    print("Error:", e)
