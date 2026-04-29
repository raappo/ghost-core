import os
import time
import re
import requests
from google import genai
from google.genai import types
from supabase import create_client

# 1. Configuration & Setup
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SB_URL = os.environ.get("SUPABASE_URL")
SB_KEY = os.environ.get("SUPABASE_KEY")

client = genai.Client(api_key=GEMINI_KEY)
supabase = create_client(SB_URL, SB_KEY)

def get_next_available_id():
    result = supabase.table("content_farm").select("id").order("id", desc=False).execute()
    existing_ids = [row['id'] for row in result.data]
    lowest_id = 1
    while lowest_id in existing_ids: lowest_id += 1
    return lowest_id

def generate_article():
    model_id = 'gemini-2.5-flash'
    target_id = get_next_available_id()
    
    # SYSTEM PROMPT: Forces high-end journalistic structure
    prompt = """
    Write a professional tech news article for April 29, 2026.
    Structure:
    - TITLE: [Catchy, non-clickbait title]
    - CATEGORY: [Breaking, Deep Dive, or Analysis]
    - SUMMARY: [Professional 2-sentence summary]
    - IMAGE_PROMPT: [3 keywords for a tech image related to this topic]
    - BODY: [1200 words of formatted markdown. Use ## for headers. Use bolding. Use lists.]
    - CONCLUSION: [Final thoughts]
    """

    # Retry Logic for 503 Spikes
    response = None
    for _ in range(3):
        try:
            response = client.models.generate_content(
                model=model_id, contents=prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            break
        except: time.sleep(20)

    if not response: return

    # Parse AI Response
    text = response.text
    try:
        title = re.search(r"TITLE: (.*)", text).group(1)
        category = re.search(r"CATEGORY: (.*)", text).group(1)
        summary = re.search(r"SUMMARY: (.*)", text).group(1)
        img_keywords = re.search(r"IMAGE_PROMPT: (.*)", text).group(1).replace(" ", ",")
        body = text.split("BODY:")[1].split("CONCLUSION:")[0].strip()
        conclusion = text.split("CONCLUSION:")[1].strip()
    except:
        # Fallback if AI skips a label
        title, category, summary, img_keywords, body, conclusion = "Tech Update 2026", "Breaking", "Latest news.", "technology", text, "End of report."

    # 2. Fetch Professional Image
    img_url = f"https://source.unsplash.com/1600x900/?{img_keywords},tech"
    # Note: Using unpslash source for direct hotlinking in 2026

    # 3. Save to Brain (Supabase)
    post_data = {
        "id": target_id,
        "title": title,
        "body_content": text, # Raw for future re-renders
        "domain_name": "news.raappo.cf"
    }
    supabase.table("content_farm").insert(post_data).execute()

    # 4. SITE BUILDER ENGINE
    all_posts = supabase.table("content_farm").select("*").order("created_at", desc=True).execute().data
    if not os.path.exists('posts'): os.makedirs('posts')

    # Build Article Library (Grid HTML)
    grid_html = ""
    for post in all_posts:
        p_id = post['id']
        p_title = post['title']
        p_date = post['created_at'][:10]
        grid_html += f"""
        <a href="posts/post_{p_id}.html" class="group block bg-white border border-gray-100 rounded-2xl overflow-hidden hover:border-blue-500 transition-all duration-300">
            <div class="aspect-video bg-gray-100 overflow-hidden">
                <img src="https://source.unsplash.com/800x450/?tech,code,{p_id}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500">
            </div>
            <div class="p-6">
                <div class="flex items-center gap-3 mb-3">
                    <span class="px-2 py-1 bg-blue-50 text-blue-600 text-[10px] font-bold uppercase rounded">Breaking</span>
                    <span class="text-gray-400 text-[10px] font-medium">{p_date}</span>
                </div>
                <h3 class="text-lg font-bold text-gray-900 group-hover:text-blue-600 line-clamp-2">{p_title}</h3>
            </div>
        </a>
        """

    # Generate Individual Post Pages
    for post in all_posts:
        render_post_page(post, img_url if post['id'] == target_id else f"https://source.unsplash.com/1600x900/?tech,{post['id']}")

    # Generate Main Homepage
    hero = all_posts[0]
    homepage_html = f"""
    <div class="mb-20">
        <div class="relative rounded-[2rem] overflow-hidden bg-slate-900 min-h-[500px] flex items-center">
            <img src="{img_url}" class="absolute inset-0 w-full h-full object-cover opacity-50">
            <div class="relative z-10 p-8 md:p-20 max-w-4xl">
                <span class="inline-block px-4 py-1.5 bg-blue-600 text-white text-xs font-black uppercase tracking-widest rounded-full mb-6">Featured Headline</span>
                <h1 class="text-4xl md:text-7xl font-black text-white mb-8 leading-[1.1]">{hero['title']}</h1>
                <p class="text-xl text-gray-200 mb-10 line-clamp-2">{summary}</p>
                <a href="posts/post_{hero['id']}.html" class="inline-flex items-center gap-3 bg-white text-black px-8 py-4 rounded-full font-bold hover:bg-blue-600 hover:text-white transition-all group">
                    Explore Report
                    <span class="group-hover:translate-x-1 transition-transform">→</span>
                </a>
            </div>
        </div>
    </div>
    <div class="flex items-center justify-between mb-10">
        <h2 class="text-3xl font-black tracking-tight">Recent <span class="text-blue-600">Intelligence</span></h2>
        <div class="h-[1px] flex-grow mx-8 bg-gray-100"></div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10">
        {grid_html}
    </div>
    """
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(render_base_template(title, homepage_html, is_home=True))

def render_post_page(post, img_url):
    # Process the body into beautiful HTML
    body_html = post['body_content'].replace("## ", '<h2 class="text-3xl font-bold mt-12 mb-6 text-gray-900">').replace("\n\n", "</p><p class='mb-6 text-gray-600 text-lg leading-relaxed'>")
    
    content = f"""
    <article class="max-w-4xl mx-auto">
        <header class="mb-12 text-center">
            <div class="flex justify-center gap-4 mb-6">
                <span class="text-blue-600 font-bold uppercase tracking-widest text-xs">Technical Analysis</span>
                <span class="text-gray-300">•</span>
                <span class="text-gray-500 font-medium text-xs">{post['created_at'][:10]}</span>
            </div>
            <h1 class="text-4xl md:text-6xl font-black leading-tight mb-8">{post['title']}</h1>
        </header>
        <img src="{img_url}" class="w-full aspect-video object-cover rounded-3xl mb-16 shadow-2xl">
        <div class="prose prose-slate max-w-none">
            {body_html}
        </div>
    </article>
    """
    with open(f"posts/post_{post['id']}.html", "w", encoding="utf-8") as f:
        f.write(render_base_template(post['title'], content, is_home=False))

def render_base_template(title, content, is_home=True):
    root = "" if is_home else "../"
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title} | RAAPPO</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;700;800&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Plus Jakarta Sans', sans-serif; scroll-behavior: smooth; }}
            .line-clamp-2 {{ display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
        </style>
    </head>
    <body class="bg-[#fafafa] text-[#1a1a1a]">
        <nav class="sticky top-0 z-[100] bg-white/80 backdrop-blur-xl border-b border-gray-100">
            <div class="max-w-7xl mx-auto px-6 h-24 flex items-center justify-between">
                <a href="{root}index.html" class="text-3xl font-extrabold tracking-tighter hover:text-blue-600 transition">RAAPPO<span class="text-blue-600">.</span></a>
                <div class="hidden lg:flex items-center gap-10">
                    <a href="{root}index.html" class="text-xs font-black uppercase tracking-[0.2em] text-gray-400 hover:text-blue-600 transition">Trending</a>
                    <a href="{root}index.html" class="text-xs font-black uppercase tracking-[0.2em] text-gray-400 hover:text-blue-600 transition">Reports</a>
                    <a href="{root}index.html" class="text-xs font-black uppercase tracking-[0.2em] text-gray-400 hover:text-blue-600 transition">The Archive</a>
                </div>
                <div class="flex items-center gap-6">
                    <span class="hidden md:block text-[10px] font-bold text-gray-400 bg-gray-100 px-3 py-1 rounded-full uppercase tracking-widest">LIVE 2026 FEED</span>
                    <button class="w-10 h-10 flex items-center justify-center bg-black text-white rounded-full hover:bg-blue-600 transition">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                    </button>
                </div>
            </div>
        </nav>
        <main class="max-w-7xl mx-auto px-6 py-16">
            {content}
        </main>
        <footer class="bg-white border-t border-gray-100 pt-24 pb-12">
            <div class="max-w-7xl mx-auto px-6">
                <div class="grid grid-cols-1 md:grid-cols-4 gap-16 mb-20">
                    <div class="col-span-2">
                        <div class="text-3xl font-black tracking-tighter mb-6">RAAPPO<span class="text-blue-600">.</span></div>
                        <p class="text-gray-500 text-lg leading-relaxed max-w-md">Decentralized autonomous news network delivering 2026's most vital technological intelligence.</p>
                    </div>
                    <div>
                        <h4 class="font-bold uppercase tracking-widest text-xs text-gray-400 mb-6">Navigation</h4>
                        <ul class="space-y-4 font-bold text-sm">
                            <li><a href="{root}index.html" class="hover:text-blue-600 transition">Front Page</a></li>
                            <li><a href="{root}index.html" class="hover:text-blue-600 transition">Latest Trends</a></li>
                        </ul>
                    </div>
                    <div>
                        <h4 class="font-bold uppercase tracking-widest text-xs text-gray-400 mb-6">System Status</h4>
                        <div class="flex items-center gap-2 text-green-500 text-xs font-black uppercase">
                            <span class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
                            Operational
                        </div>
                    </div>
                </div>
                <div class="border-t border-gray-100 pt-12 flex flex-col md:flex-row justify-between items-center gap-6">
                    <p class="text-gray-400 text-xs font-medium">© 2026 RAAPPO GLOBAL. ALL DATA SECURED VIA SUPABASE.</p>
                    <div class="flex gap-8 text-xs font-black uppercase tracking-widest text-gray-400">
                        <a href="#">Privacy</a><a href="#">Terms</a><a href="#">RSS</a>
                    </div>
                </div>
            </div>
        </footer>
    </body>
    </html>
    """

if __name__ == "__main__":
    generate_article()
