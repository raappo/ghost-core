import os
from google import genai
from google.genai import types
from supabase import create_client

# 1. Setup
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SB_URL = os.environ.get("SUPABASE_URL")
SB_KEY = os.environ.get("SUPABASE_KEY")

client = genai.Client(api_key=GEMINI_KEY)
supabase = create_client(SB_URL, SB_KEY)

def generate_article():
    # A. Generate the Newest Article
    model_id = 'gemini-2.5-flash'
    prompt = "Research a trending tech story for today, April 29, 2026. Write a catchy title and an 800-word SEO article in HTML (h2, p, li)."
    
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
    )
    
    # B. Save the new article to the Brain (Supabase)
    new_post = {
        "domain_name": "news.raappo.cf",
        "title": response.text.split('</h2>')[0].replace('<h2>', '').strip()[:50], # Tiny logic to grab a title
        "body_content": response.text
    }
    supabase.table("content_farm").insert(new_post).execute()

    # C. FETCH ALL POSTS FROM DB (The Library)
    all_posts = supabase.table("content_farm").select("*").order("created_at", desc=True).execute()

    # D. BUILD INDIVIDUAL POST PAGES
    if not os.path.exists('posts'): os.makedirs('posts')
    
    menu_html = ""
    for post in all_posts.data:
        file_name = f"post_{post['id']}.html"
        menu_html += f'<li><a href="posts/{file_name}">{post["title"]}</a> - <small>{post["created_at"][:10]}</small></li>'
        
        with open(f"posts/{file_name}", "w", encoding="utf-8") as f:
            f.write(f"""
            <html>
            <head><title>{post['title']}</title>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css">
            </head>
            <body class="container">
                <nav><ul><li><strong><a href="../index.html">← Back to Home</a></strong></li></ul></nav>
                {post['body_content']}
            </body>
            </html>
            """)

    # E. BUILD THE MAIN HOME PAGE (The Menu)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(f"""
        <html>
        <head><title>Raappo Ghost Industry News</title>
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@1/css/pico.min.css">
        </head>
        <body class="container">
            <header>
                <h1>🚀 Raappo Tech Pulse</h1>
                <p>Automated 2026 Intelligence Feed</p>
            </header>
            <main>
                <h2>Latest Archive</h2>
                <ul>{menu_html}</ul>
            </main>
        </body>
        </html>
        """)

if __name__ == "__main__":
    generate_article()
