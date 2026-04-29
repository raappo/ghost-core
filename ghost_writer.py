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

def get_next_available_id():
    """Custom logic to fill gaps in IDs"""
    result = supabase.table("content_farm").select("id").order("id", desc=False).execute()
    existing_ids = [row['id'] for row in result.data]
    
    lowest_id = 1
    while lowest_id in existing_ids:
        lowest_id += 1
    return lowest_id

def generate_article():
    model_id = 'gemini-2.5-flash'
    target_id = get_next_available_id()
    
    prompt = """
    Act as a professional tech journalist for XDA-Developers or The Verge.
    Topic: A major real-world tech breakthrough from today, April 29, 2026.
    
    Structure the response in CLEAN MARKDOWN (no HTML tags in the raw AI response).
    Include:
    1. A short, punchy Title.
    2. A brief 2-sentence Summary (Subtitle).
    3. The main article body with multiple ## Subheadings.
    4. Use bullet points for key specs.
    5. A 'The Bottom Line' conclusion.
    
    Do NOT mention AI, automation, or yourself. Make it 1000+ words.
    """

    # Retry Loop for 503 Errors
    response = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            break
        except Exception as e:
            print(f"Server busy, retrying... {e}")
            time.sleep(30)

    if not response: return

    # Splitting logic to handle the clean UI
    raw_text = response.text
    lines = raw_text.split('\n')
    title = lines[0].replace('# ', '').strip()
    subtitle = lines[2] if len(lines) > 2 else "Expert analysis on the latest tech shift."
    body_markdown = "\n".join(lines[3:])

    # 2. Save to Database with the RECYCLED ID
    new_post = {
        "id": target_id,
        "domain_name": "news.raappo.cf",
        "title": title,
        "body_content": raw_text # Store raw for processing
    }
    supabase.table("content_farm").insert(new_post).execute()

    # 3. Rebuild the Entire Multi-page Site
    all_posts = supabase.table("content_farm").select("*").order("created_at", desc=True).execute().data
    if not os.path.exists('posts'): os.makedirs('posts')

    # Build Index Grid
    post_cards_html = ""
    for post in all_posts:
        # Use a random tech image based on title
        img_url = f"https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=800&q=80"
        file_name = f"post_{post['id']}.html"
        post_cards_html += f"""
        <div class="flex flex-col bg-white border border-gray-200 rounded-xl overflow-hidden hover:shadow-lg transition">
            <img src="{img_url}" class="h-48 w-full object-cover">
            <div class="p-5">
                <p class="text-blue-600 text-xs font-bold uppercase tracking-tighter mb-2">Editor's Choice</p>
                <h3 class="text-xl font-bold mb-2 hover:text-blue-600"><a href="posts/{file_name}">{post['title']}</a></h3>
                <p class="text-gray-500 text-sm line-clamp-2">Leading global insights for the year 2026.</p>
            </div>
        </div>
        """
        # Generate Individual Page
        with open(f"posts/{file_name}", "w", encoding="utf-8") as f:
            f.write(render_template(post['title'], post['body_content'], is_home=False))

    # Build Home Page
    hero = all_posts[0]
    hero_html = f"""
    <div class="grid lg:grid-cols-2 gap-0 bg-black text-white rounded-3xl overflow-hidden mb-16">
        <img src="https://images.unsplash.com/photo-1451187580459-43490279c0fa?auto=format&fit=crop&w=1200&q=80" class="h-full w-full object-cover opacity-80">
        <div class="p-12 flex flex-col justify-center">
            <span class="text-blue-400 font-bold tracking-widest text-sm mb-4">LATEST BREAKING</span>
            <h1 class="text-4xl md:text-5xl font-black mb-6 leading-tight">{hero['title']}</h1>
            <a href="posts/post_{hero['id']}.html" class="bg-blue-600 w-fit px-8 py-3 rounded-md font-bold hover:bg-blue-700 transition">Read Full Coverage</a>
        </div>
    </div>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(render_template("Raappo | Tech News & Analysis", hero_html + f'<div class="grid md:grid-cols-3 gap-8">{post_cards_html}</div>', is_home=True))

def render_template(title, content, is_home=True):
    path = "" if is_home else "../"
    # Basic Markdown to HTML conversion for sections
    styled_content = content.replace("## ", '<h2 class="text-2xl font-bold mt-10 mb-4 text-slate-800">').replace("\n\n", "</p><p class='mb-6 leading-relaxed'>")
    
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;700;900&display=swap" rel="stylesheet">
        <style>body {{ font-family: 'Archivo', sans-serif; }}</style>
    </head>
    <body class="bg-white text-slate-900">
        <nav class="border-b border-gray-100 h-20 flex items-center sticky top-0 bg-white/95 backdrop-blur-sm z-50">
            <div class="max-w-7xl mx-auto px-6 w-full flex items-center justify-between">
                <div class="flex items-center space-x-10">
                    <a href="{path}index.html" class="text-2xl font-black italic tracking-tighter">RAAPPO<span class="text-blue-600">.</span></a>
                    <div class="hidden md:flex space-x-6 text-[11px] font-black uppercase tracking-widest text-slate-400">
                        <a href="{path}index.html" class="hover:text-blue-600 transition">Mobile</a>
                        <a href="{path}index.html" class="hover:text-blue-600 transition">Computing</a>
                        <a href="{path}index.html" class="hover:text-blue-600 transition">Devs</a>
                    </div>
                </div>
                <div class="flex items-center space-x-4">
                    <div class="h-8 w-8 bg-slate-100 rounded-full flex items-center justify-center cursor-pointer hover:bg-slate-200">🔍</div>
                </div>
            </div>
        </nav>
        <main class="max-w-7xl mx-auto px-6 py-12">
            {styled_content}
        </main>
        <footer class="bg-slate-50 border-t border-gray-100 py-16 mt-20">
            <div class="max-w-7xl mx-auto px-6 grid md:grid-cols-4 gap-12">
                <div class="col-span-2">
                    <a href="{path}index.html" class="text-xl font-black italic">RAAPPO.</a>
                    <p class="text-slate-400 text-sm mt-4 max-w-sm">The world's leading authority on 2026 technological advancements and analysis.</p>
                </div>
                <div>
                    <h4 class="font-bold mb-4">Resources</h4>
                    <ul class="text-slate-400 text-sm space-y-2"><li>Newsletter</li><li>Contact</li><li>Privacy</li></ul>
                </div>
                <p class="text-slate-300 text-xs mt-10">© 2026 RAAPPO Media. All rights reserved.</p>
            </div>
        </footer>
    </body>
    </html>
    """

if __name__ == "__main__":
    generate_article()
