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
    # A. The Journalist Brain - Generating High-Quality Content
    model_id = 'gemini-2.5-flash'
    prompt = """
    Act as a Senior Tech Editor for a major news outlet like Wired or TechCrunch. 
    Research a major tech breakthrough or trend for today, April 29, 2026.
    Write a 1200-word, highly engaging, and professional article.
    Use proper journalistic subheadings (h2, h3). 
    Do NOT mention that you are an AI or that this is automated. 
    Start the response directly with the Article Title inside an <h1> tag, followed by the content.
    """
    
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
    )
    
    full_content = response.text
    title = full_content.split('</h1>')[0].replace('<h1>', '').strip()

    # B. Save to Database
    new_post = {
        "domain_name": "news.raappo.cf",
        "title": title,
        "body_content": full_content
    }
    supabase.table("content_farm").insert(new_post).execute()

    # C. Fetch Library
    all_posts = supabase.table("content_farm").select("*").order("created_at", desc=True).execute().data

    # D. Build the Multipage Infrastructure
    if not os.path.exists('posts'): os.makedirs('posts')
    
    # Generate individual article pages
    post_cards_html = ""
    for i, post in enumerate(all_posts):
        file_name = f"post_{post['id']}.html"
        # Create a card for the home page grid
        post_cards_html += f"""
        <div class="bg-white rounded-lg shadow-sm overflow-hidden border border-gray-100 hover:shadow-md transition">
            <div class="p-6">
                <span class="text-blue-600 text-xs font-bold uppercase tracking-widest">Technology</span>
                <h3 class="mt-2 text-xl font-bold text-gray-900"><a href="posts/{file_name}">{post['title']}</a></h3>
                <p class="mt-3 text-gray-500 text-sm line-clamp-3">Deep dive into the latest developments shaping the year 2026.</p>
                <div class="mt-4 flex items-center text-xs text-gray-400">
                    <span>{post['created_at'][:10]}</span>
                    <span class="mx-2">•</span>
                    <span>8 min read</span>
                </div>
            </div>
        </div>
        """
        
        # Write the individual page
        with open(f"posts/{file_name}", "w", encoding="utf-8") as f:
            f.write(render_template(post['title'], post['body_content'], is_home=False))

    # E. Build the Magazine Home Page
    hero_post = all_posts[0]
    hero_html = f"""
    <section class="relative bg-gray-900 text-white py-20 px-6 rounded-3xl overflow-hidden mb-12">
        <div class="relative z-10 max-w-3xl">
            <span class="bg-blue-600 text-white px-3 py-1 rounded-full text-xs font-bold uppercase tracking-widest">Featured Story</span>
            <h2 class="mt-6 text-4xl md:text-5xl font-extrabold leading-tight">{hero_post['title']}</h2>
            <p class="mt-6 text-lg text-gray-300 line-clamp-3">Leading the narrative in 2026: A comprehensive analysis of today's most significant technological shift.</p>
            <a href="posts/post_{hero_post['id']}.html" class="mt-8 inline-block bg-white text-gray-900 px-8 py-3 rounded-full font-bold hover:bg-blue-50 transition">Read Article</a>
        </div>
    </section>
    """

    home_content = hero_html + f'<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">{post_cards_html}</div>'
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(render_template("Raappo Tech Pulse | 2026 Intelligence", home_content, is_home=True))

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
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;800&display=swap" rel="stylesheet">
        <style>body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}</style>
    </head>
    <body class="bg-slate-50 text-slate-900">
        <nav class="bg-white border-b border-gray-100 sticky top-0 z-50">
            <div class="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
                <a href="{path_prefix}index.html" class="text-2xl font-extrabold tracking-tighter text-slate-900">RAAPPO<span class="text-blue-600">.</span></a>
                <div class="hidden md:flex space-x-8 text-sm font-bold uppercase tracking-widest text-gray-500">
                    <a href="#" class="hover:text-blue-600 transition">Intelligence</a>
                    <a href="#" class="hover:text-blue-600 transition">Analysis</a>
                    <a href="#" class="hover:text-blue-600 transition">Future Tech</a>
                    <a href="#" class="hover:text-blue-600 transition">About</a>
                </div>
                <button class="bg-blue-600 text-white px-6 py-2 rounded-full text-sm font-bold">Subscribe</button>
            </div>
        </nav>
        <main class="max-w-7xl mx-auto px-6 py-12">
            {content}
        </main>
        <footer class="bg-white border-t border-gray-100 py-12 mt-20">
            <div class="max-w-7xl mx-auto px-6 text-center">
                <p class="text-gray-400 text-sm">© 2026 Raappo Global Media. All editorial rights reserved.</p>
            </div>
        </footer>
    </body>
    </html>
    """

if __name__ == "__main__":
    generate_article()
