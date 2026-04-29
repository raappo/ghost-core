import os
import time
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
    model_id = 'gemini-2.5-flash'
    prompt = """
    Act as a Senior Tech Editor. Research a major tech breakthrough for today, April 29, 2026.
    Write a 1200-word, professional article in HTML (h2, p, li).
    Start directly with the title in <h1>. No AI mentions.
    """

    # --- Robust Retry Loop ---
    response = None
    for attempt in range(3): # Try 3 times
        try:
            print(f"Attempt {attempt + 1}: Contacting the AI Brain...")
            response = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                )
            )
            break # If successful, exit the loop
        except Exception as e:
            if "503" in str(e) or "demand" in str(e).lower():
                print("Server busy. Waiting 30 seconds to retry...")
                time.sleep(30)
            else:
                raise e # If it's a different error, stop.

    if not response:
        print("Google servers are too busy right now. Try again in an hour.")
        return

    full_content = response.text
    title = full_content.split('</h1>')[0].replace('<h1>', '').strip()

    # 2. Save to Database
    new_post = {
        "domain_name": "news.raappo.cf",
        "title": title,
        "body_content": full_content
    }
    supabase.table("content_farm").insert(new_post).execute()

    # 3. Fetch all posts to rebuild the magazine
    all_posts = supabase.table("content_farm").select("*").order("created_at", desc=True).execute().data

    # 4. Build the Infrastructure
    if not os.path.exists('posts'): os.makedirs('posts')
    
    post_cards_html = ""
    for post in all_posts:
        file_name = f"post_{post['id']}.html"
        post_cards_html += f"""
        <div class="bg-white rounded-lg shadow-sm overflow-hidden border border-gray-100 hover:shadow-md transition">
            <div class="p-6">
                <span class="text-blue-600 text-xs font-bold uppercase tracking-widest">Global Tech</span>
                <h3 class="mt-2 text-xl font-bold text-gray-900"><a href="posts/{file_name}">{post['title']}</a></h3>
                <div class="mt-4 flex items-center text-xs text-gray-400">
                    <span>{post['created_at'][:10]}</span>
                    <span class="mx-2">•</span>
                    <span>10 min read</span>
                </div>
            </div>
        </div>
        """
        with open(f"posts/{file_name}", "w", encoding="utf-8") as f:
            f.write(render_template(post['title'], post['body_content'], is_home=False))

    # 5. Build Home Page
    hero_post = all_posts[0]
    hero_html = f"""
    <section class="relative bg-slate-900 text-white py-24 px-8 rounded-3xl overflow-hidden mb-12 shadow-2xl">
        <div class="relative z-10 max-w-3xl">
            <span class="bg-blue-500 text-white px-4 py-1 rounded-full text-xs font-bold uppercase tracking-widest">Breaking Analysis</span>
            <h2 class="mt-8 text-4xl md:text-6xl font-extrabold leading-tight">{hero_post['title']}</h2>
            <a href="posts/post_{hero_post['id']}.html" class="mt-10 inline-block bg-white text-slate-900 px-10 py-4 rounded-full font-bold hover:bg-blue-400 hover:text-white transition-all text-lg">Read the Full Report</a>
        </div>
    </section>
    """
    home_content = hero_html + f'<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10">{post_cards_html}</div>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(render_template("Raappo Intelligence | 2026 Global News", home_content, is_home=True))

def render_template(title, content, is_home=True):
    path_prefix = "" if is_home else "../"
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;600;900&display=swap" rel="stylesheet">
        <style>body {{ font-family: 'Outfit', sans-serif; }}</style>
    </head>
    <body class="bg-gray-50 text-slate-900">
        <nav class="bg-white/80 backdrop-blur-md border-b border-gray-100 sticky top-0 z-50 h-24 flex items-center">
            <div class="max-w-7xl mx-auto px-8 w-full flex items-center justify-between">
                <a href="{path_prefix}index.html" class="text-3xl font-black tracking-tighter text-slate-900 italic">RAAPPO<span class="text-blue-500">.</span></a>
                <div class="hidden lg:flex space-x-12 text-sm font-bold uppercase tracking-widest text-slate-400">
                    <a href="#" class="hover:text-blue-500 transition">Markets</a>
                    <a href="#" class="hover:text-blue-500 transition">AI Ethics</a>
                    <a href="#" class="hover:text-blue-500 transition">Space Tech</a>
                </div>
                <button class="bg-slate-900 text-white px-8 py-3 rounded-full text-sm font-bold hover:bg-blue-500 transition">Membership</button>
            </div>
        </nav>
        <main class="max-w-7xl mx-auto px-8 py-16">
            {content}
        </main>
        <footer class="bg-slate-900 text-slate-500 py-20 mt-32">
            <div class="max-w-7xl mx-auto px-8 text-center">
                <p class="text-sm tracking-widest uppercase font-bold">&copy; 2026 Raappo Global Media Group</p>
            </div>
        </footer>
    </body>
    </html>
    """

if __name__ == "__main__":
    generate_article()
