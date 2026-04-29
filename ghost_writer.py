import os
from google import genai # Standard 2026 Library
from google.genai import types
from supabase import create_client

# 1. Setup Connections
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SB_URL = os.environ.get("SUPABASE_URL")
SB_KEY = os.environ.get("SUPABASE_KEY")

client = genai.Client(api_key=GEMINI_KEY)
supabase = create_client(SB_URL, SB_KEY)

def generate_article():
    # Using Gemini 2.5 Flash because it has 1.5K Search Grounding RPD
    model_id = 'gemini-2.5-flash'
    
    prompt = "Research the top tech breakthrough specifically for today, April 29, 2026. Write a 1000-word SEO article in HTML format (h2, p, li). Make it professional and ready for a news subdomain."
    
    # 2026 Syntax for Search Grounding
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )
    
    article_html = response.text
    
    # 2. Save to Supabase
    data = {
        "domain_name": "news.raappo.cf", 
        "title": "2026 Tech Pulse",
        "body_content": article_html
    }
    supabase.table("content_farm").insert(data).execute()
    
    # 3. Create the index.html for your subdomain
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <title>Raappo Ghost News</title>
            <style>
                body {{ font-family: 'Inter', sans-serif; max-width: 800px; margin: auto; padding: 50px; background: #f9f9f9; }}
                .container {{ background: white; padding: 40px; border-radius: 10px; shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                h2 {{ color: #1a73e8; }}
            </style>
        </head>
        <body>
            <div class="container">
                {article_html}
            </div>
        </body>
        </html>
        """)

if __name__ == "__main__":
    generate_article()
