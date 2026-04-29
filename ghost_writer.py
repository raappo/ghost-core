import os
import google.generativeai as genai
from supabase import create_client

# 1. Setup Connections from your GitHub Secrets
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SB_URL = os.environ.get("SUPABASE_URL")
SB_KEY = os.environ.get("SUPABASE_KEY")

genai.configure(api_key=GEMINI_KEY)
supabase = create_client(SB_URL, SB_KEY)

def generate_article():
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    # The Prompt: Telling the AI what to write
    prompt = "Write a high-quality, 800-word blog post about a trending AI tool or crypto trend in 2026. Use HTML tags for formatting (h1, h2, p). Make it very professional."
    
    response = model.generate_content(prompt)
    article_html = response.text
    
    # 2. Save to your Supabase Database
    data = {
        "domain_name": "news.raappo.cf", # Change this to your subdomain
        "title": "Daily Ghost Update",
        "body_content": article_html
    }
    supabase.table("content_farm").insert(data).execute()
    
    # 3. Create the index.html file for the website
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(f"""
        <!DOCTYPE html>
        <html lang="en">
        <head><meta charset="UTF-8"><title>Ghost News</title></head>
        <body style="font-family: sans-serif; max-width: 800px; margin: auto; padding: 20px;">
            {article_html}
        </body>
        </html>
        """)

if __name__ == "__main__":
    generate_article()
