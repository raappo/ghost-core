import os
import time
import re
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

def get_image_url(seed, width=1600, height=900):
    """Return a reliable image URL using picsum.photos with a deterministic seed."""
    safe_seed = re.sub(r'[^a-zA-Z0-9]', '', str(seed))[:24] or "tech"
    return f"https://picsum.photos/seed/{safe_seed}/{width}/{height}"

def inline_markdown(text):
    """Process inline markdown: bold, italic, inline code."""
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<strong><em>\1</em></strong>', text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong class="font-semibold text-gray-900">\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em class="italic">\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code class="bg-gray-100 text-blue-700 px-1.5 py-0.5 rounded text-sm font-mono">\1</code>', text)
    return text

def markdown_to_html(text):
    """Convert a markdown string to styled HTML."""
    lines = text.split('\n')
    html_parts = []
    in_ul = False
    in_ol = False
    in_para_lines = []

    def flush_para():
        nonlocal in_para_lines
        if in_para_lines:
            content = ' '.join(in_para_lines).strip()
            if content:
                html_parts.append(
                    f'<p class="mb-6 text-gray-700 text-lg leading-relaxed">{inline_markdown(content)}</p>'
                )
            in_para_lines = []

    def close_list():
        nonlocal in_ul, in_ol
        if in_ul:
            html_parts.append('</ul>')
            in_ul = False
        if in_ol:
            html_parts.append('</ol>')
            in_ol = False

    for line in lines:
        stripped = line.rstrip()

        # Fenced code blocks — skip through as preformatted
        if stripped.startswith('```'):
            flush_para()
            close_list()
            continue

        # ATX headers
        m = re.match(r'^(#{1,6})\s+(.*)', stripped)
        if m:
            flush_para()
            close_list()
            level = len(m.group(1))
            content = inline_markdown(m.group(2).strip())
            tag_classes = {
                1: 'text-3xl font-bold mt-12 mb-6 text-gray-900 border-b border-gray-100 pb-3',
                2: 'text-3xl font-bold mt-12 mb-6 text-gray-900 border-b border-gray-100 pb-3',
                3: 'text-2xl font-bold mt-10 mb-4 text-gray-900',
                4: 'text-xl font-bold mt-8 mb-3 text-gray-800',
                5: 'text-lg font-bold mt-6 mb-2 text-gray-800',
                6: 'text-base font-bold mt-4 mb-2 text-gray-700',
            }
            cls = tag_classes.get(level, tag_classes[2])
            tag = 'h2' if level <= 2 else f'h{level}'
            html_parts.append(f'<{tag} class="{cls}">{content}</{tag}>')
            continue

        # Unordered list items
        m = re.match(r'^[\*\-]\s+(.*)', stripped)
        if m:
            flush_para()
            if in_ol:
                html_parts.append('</ol>')
                in_ol = False
            if not in_ul:
                html_parts.append('<ul class="list-disc pl-6 mb-6 space-y-2 text-gray-700 text-lg leading-relaxed">')
                in_ul = True
            html_parts.append(f'<li>{inline_markdown(m.group(1))}</li>')
            continue

        # Ordered list items
        m = re.match(r'^\d+\.\s+(.*)', stripped)
        if m:
            flush_para()
            if in_ul:
                html_parts.append('</ul>')
                in_ul = False
            if not in_ol:
                html_parts.append('<ol class="list-decimal pl-6 mb-6 space-y-2 text-gray-700 text-lg leading-relaxed">')
                in_ol = True
            html_parts.append(f'<li>{inline_markdown(m.group(1))}</li>')
            continue

        # Empty line — flush accumulated paragraph
        if stripped == '':
            flush_para()
            close_list()
            continue

        # Regular text — accumulate for paragraph
        in_para_lines.append(stripped)

    flush_para()
    close_list()
    return '\n'.join(html_parts)

def apply_html_styles(html_content):
    """Apply Tailwind classes to unstyled HTML elements from AI-generated content."""
    # Remove inline style attributes on wrapper divs
    html_content = re.sub(r'<div\s+style="[^"]*">', '<div>', html_content)
    html_content = re.sub(r'<div\s+class="[^"]*">', '<div>', html_content)

    # h1 → styled h2 (treat all h1 inside body as section headers)
    html_content = re.sub(
        r'<h1(?![^>]*class)[^>]*>(.*?)</h1>',
        r'<h2 class="text-3xl font-bold mt-12 mb-6 text-gray-900 border-b border-gray-100 pb-3">\1</h2>',
        html_content, flags=re.DOTALL
    )
    html_content = re.sub(
        r'<h2(?![^>]*class)[^>]*>(.*?)</h2>',
        r'<h2 class="text-3xl font-bold mt-12 mb-6 text-gray-900 border-b border-gray-100 pb-3">\1</h2>',
        html_content, flags=re.DOTALL
    )
    html_content = re.sub(
        r'<h3(?![^>]*class)[^>]*>(.*?)</h3>',
        r'<h3 class="text-2xl font-bold mt-10 mb-4 text-gray-900">\1</h3>',
        html_content, flags=re.DOTALL
    )
    html_content = re.sub(
        r'<h4(?![^>]*class)[^>]*>(.*?)</h4>',
        r'<h4 class="text-xl font-bold mt-8 mb-3 text-gray-800">\1</h4>',
        html_content, flags=re.DOTALL
    )
    html_content = re.sub(
        r'<p(?![^>]*class)[^>]*>(.*?)</p>',
        r'<p class="mb-6 text-gray-700 text-lg leading-relaxed">\1</p>',
        html_content, flags=re.DOTALL
    )
    html_content = re.sub(
        r'<ul(?![^>]*class)[^>]*>',
        r'<ul class="list-disc pl-6 mb-6 space-y-2 text-gray-700 text-lg leading-relaxed">',
        html_content
    )
    html_content = re.sub(
        r'<ol(?![^>]*class)[^>]*>',
        r'<ol class="list-decimal pl-6 mb-6 space-y-2 text-gray-700 text-lg leading-relaxed">',
        html_content
    )
    html_content = re.sub(
        r'<li(?![^>]*class)[^>]*>',
        r'<li class="leading-relaxed">',
        html_content
    )
    html_content = re.sub(
        r'<strong(?![^>]*class)[^>]*>(.*?)</strong>',
        r'<strong class="font-semibold text-gray-900">\1</strong>',
        html_content, flags=re.DOTALL
    )
    # Convert any remaining bare **bold** markdown inside HTML
    html_content = re.sub(r'\*\*(.+?)\*\*', r'<strong class="font-semibold text-gray-900">\1</strong>', html_content)
    return html_content

def process_body_content(raw_content):
    """
    Convert raw AI response (structured markdown, plain markdown, or HTML) to
    clean, fully-styled HTML ready for the article page.
    """
    text = raw_content.strip()

    # Handle the case where AI returned a full HTML document
    if re.search(r'<html', text, re.IGNORECASE):
        body_match = re.search(r'<body[^>]*>(.*?)</body>', text, re.DOTALL | re.IGNORECASE)
        if body_match:
            text = body_match.group(1).strip()
        else:
            text = re.sub(
                r'</?html[^>]*>|<head>.*?</head>|</?body[^>]*>',
                '', text, flags=re.DOTALL | re.IGNORECASE
            ).strip()

    # Extract BODY / CONCLUSION sections from structured prompt format
    if 'BODY:' in text:
        after_body = text.split('BODY:', 1)[1]
        if 'CONCLUSION:' in after_body:
            body_text, conclusion_text = after_body.split('CONCLUSION:', 1)
        else:
            body_text, conclusion_text = after_body, ''
        text = body_text.strip()
        if conclusion_text.strip():
            text += '\n\n## In Conclusion\n\n' + conclusion_text.strip()

    # Strip any leftover metadata labels
    text = re.sub(r'^(TITLE|CATEGORY|SUMMARY|IMAGE_PROMPT):.*\n?', '', text, flags=re.MULTILINE)
    text = text.strip()

    # Detect whether content is HTML or markdown and process accordingly
    if re.search(r'<(h[1-6]|ul|ol|blockquote|table)\b', text, re.IGNORECASE):
        return apply_html_styles(text)
    else:
        return markdown_to_html(text)

def generate_article():
    model_id = 'gemini-2.5-flash'
    target_id = get_next_available_id()

    # SYSTEM PROMPT: Forces high-end journalistic structure
    prompt = """
    Write a professional tech news article for today's date in 2026.
    Return ONLY in this exact format with no extra commentary:
    TITLE: [Catchy, non-clickbait title]
    CATEGORY: [Breaking, Deep Dive, or Analysis]
    SUMMARY: [Professional 2-sentence summary]
    IMAGE_PROMPT: [3 keywords for a tech image related to this topic, no spaces, comma-separated]
    BODY:
    [1200 words of formatted markdown. Use ## for H2 headers. Use ### for H3 headers. Use **bold** for emphasis. Use bullet lists with - prefix. Write in paragraphs separated by blank lines.]
    CONCLUSION:
    [2-3 sentences of final thoughts]
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
        except:
            time.sleep(20)

    if not response:
        return

    # Parse AI Response
    text = response.text
    try:
        title = re.search(r"TITLE:\s*(.*)", text).group(1).strip()
        category = re.search(r"CATEGORY:\s*(.*)", text).group(1).strip()
        summary = re.search(r"SUMMARY:\s*(.*)", text).group(1).strip()
        img_seed = re.search(r"IMAGE_PROMPT:\s*(.*)", text).group(1).strip().replace(',', '').replace(' ', '')[:20]
    except:
        title, category, summary, img_seed = "Tech Intelligence 2026", "Breaking", "Latest tech developments.", "technology2026"

    img_url = get_image_url(img_seed)

    # 3. Save to Brain (Supabase)
    post_data = {
        "id": target_id,
        "title": title,
        "body_content": text,  # Raw AI response for future re-renders
        "domain_name": "news.raappo.cf"
    }
    supabase.table("content_farm").insert(post_data).execute()

    # 4. SITE BUILDER ENGINE
    all_posts = supabase.table("content_farm").select("*").order("created_at", desc=True).execute().data
    if not os.path.exists('posts'):
        os.makedirs('posts')

    # Build Article Grid HTML
    grid_html = ""
    for post in all_posts:
        p_id = post['id']
        p_title = post['title']
        p_date = post['created_at'][:10]
        thumb_url = get_image_url(f"raappo{p_id}", width=800, height=450)
        grid_html += f"""
        <a href="posts/post_{p_id}.html" class="group block bg-white border border-gray-100 rounded-2xl overflow-hidden hover:shadow-xl hover:border-blue-200 transition-all duration-300">
            <div class="aspect-video bg-gray-100 overflow-hidden">
                <img src="{thumb_url}" alt="{p_title}" loading="lazy" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500">
            </div>
            <div class="p-6">
                <div class="flex items-center gap-3 mb-3">
                    <span class="px-2 py-1 bg-blue-50 text-blue-600 text-[10px] font-bold uppercase tracking-wide rounded-full">Breaking</span>
                    <span class="text-gray-400 text-[10px] font-medium">{p_date}</span>
                </div>
                <h3 class="text-lg font-bold text-gray-900 group-hover:text-blue-600 line-clamp-2 leading-snug">{p_title}</h3>
                <p class="mt-3 text-sm text-gray-500 font-medium flex items-center gap-1">Read more <span class="group-hover:translate-x-1 transition-transform inline-block">→</span></p>
            </div>
        </a>
        """

    # Generate Individual Post Pages
    for post in all_posts:
        post_img = img_url if post['id'] == target_id else get_image_url(f"post{post['id']}")
        render_post_page(post, post_img)

    # Generate Main Homepage
    hero = all_posts[0]
    hero_img = img_url
    homepage_html = f"""
    <div class="mb-20">
        <div class="relative rounded-[2rem] overflow-hidden bg-slate-900 min-h-[520px] flex items-end">
            <img src="{hero_img}" alt="{hero['title']}" class="absolute inset-0 w-full h-full object-cover opacity-40">
            <div class="absolute inset-0 bg-gradient-to-t from-slate-900 via-slate-900/60 to-transparent"></div>
            <div class="relative z-10 p-8 md:p-16 max-w-4xl">
                <span class="inline-block px-4 py-1.5 bg-blue-600 text-white text-xs font-black uppercase tracking-widest rounded-full mb-5">Featured Headline</span>
                <h2 class="text-3xl md:text-6xl font-black text-white mb-6 leading-[1.1]">{hero['title']}</h2>
                <p class="text-lg text-gray-300 mb-8 max-w-2xl line-clamp-3">{summary}</p>
                <a href="posts/post_{hero['id']}.html" class="inline-flex items-center gap-3 bg-white text-black px-8 py-4 rounded-full font-bold hover:bg-blue-600 hover:text-white transition-all group">
                    Read Full Report
                    <span class="group-hover:translate-x-1 transition-transform">→</span>
                </a>
            </div>
        </div>
    </div>
    <div class="flex items-center gap-6 mb-10">
        <h2 class="text-3xl font-black tracking-tight whitespace-nowrap">Recent <span class="text-blue-600">Intelligence</span></h2>
        <div class="h-px flex-grow bg-gray-200"></div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {grid_html}
    </div>
    """

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(render_base_template("RAAPPO — Tech Intelligence 2026", homepage_html, is_home=True))

def render_post_page(post, img_url):
    """Render a single post page from a Supabase post record."""
    body_html = process_body_content(post['body_content'])
    post_date = post['created_at'][:10]
    post_title = post['title']

    content = f"""
    <div class="max-w-4xl mx-auto">
        <nav class="mb-10 text-sm font-medium text-gray-500 flex items-center gap-2">
            <a href="../index.html" class="hover:text-blue-600 transition">Home</a>
            <span class="text-gray-300">/</span>
            <span class="text-gray-800 truncate max-w-xs">{post_title}</span>
        </nav>
        <article>
            <header class="mb-10">
                <div class="flex items-center gap-3 mb-5">
                    <span class="px-3 py-1 bg-blue-600 text-white text-xs font-bold uppercase tracking-widest rounded-full">Technical Analysis</span>
                    <span class="text-gray-400 text-sm">{post_date}</span>
                    <span class="text-gray-300">·</span>
                    <span class="text-gray-400 text-sm">5 min read</span>
                </div>
                <h1 class="text-4xl md:text-5xl font-black leading-tight text-gray-900 mb-6">{post_title}</h1>
            </header>
            <figure class="mb-12">
                <img src="{img_url}" alt="{post_title}" class="w-full aspect-video object-cover rounded-2xl shadow-xl">
            </figure>
            <div class="article-content">
                {body_html}
            </div>
            <footer class="mt-16 pt-8 border-t border-gray-100 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <a href="../index.html" class="inline-flex items-center gap-2 text-blue-600 font-bold hover:gap-3 transition-all">
                    <span>←</span> Back to all articles
                </a>
                <span class="text-xs text-gray-400 uppercase tracking-widest font-bold">RAAPPO · Tech Intelligence</span>
            </footer>
        </article>
    </div>
    """
    with open(f"posts/post_{post['id']}.html", "w", encoding="utf-8") as f:
        f.write(render_base_template(post_title, content, is_home=False))

def render_base_template(title, content, is_home=True):
    root = "" if is_home else "../"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | RAAPPO</title>
    <meta name="description" content="RAAPPO — Decentralized autonomous tech intelligence for 2026.">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&family=Lora:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
    <style>
        body {{ font-family: 'Plus Jakarta Sans', sans-serif; scroll-behavior: smooth; }}
        .line-clamp-2 {{ display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
        .line-clamp-3 {{ display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}

        /* ── Article body typography ── */
        .article-content {{ font-family: 'Lora', Georgia, serif; color: #374151; }}
        .article-content p  {{ font-size: 1.125rem; line-height: 1.85; margin-bottom: 1.5rem; color: #374151; }}
        .article-content h2 {{ font-family: 'Plus Jakarta Sans', sans-serif; font-size: 1.75rem; font-weight: 800; color: #111827; margin-top: 3rem; margin-bottom: 1.25rem; padding-bottom: 0.5rem; border-bottom: 2px solid #f3f4f6; }}
        .article-content h3 {{ font-family: 'Plus Jakarta Sans', sans-serif; font-size: 1.375rem; font-weight: 700; color: #1f2937; margin-top: 2.25rem; margin-bottom: 1rem; }}
        .article-content h4 {{ font-family: 'Plus Jakarta Sans', sans-serif; font-size: 1.125rem; font-weight: 700; color: #374151; margin-top: 1.75rem; margin-bottom: 0.75rem; }}
        .article-content ul {{ list-style: disc; padding-left: 1.75rem; margin-bottom: 1.5rem; }}
        .article-content ol {{ list-style: decimal; padding-left: 1.75rem; margin-bottom: 1.5rem; }}
        .article-content li {{ font-size: 1.05rem; line-height: 1.8; margin-bottom: 0.5rem; color: #374151; }}
        .article-content strong {{ font-weight: 700; color: #111827; font-family: 'Plus Jakarta Sans', sans-serif; }}
        .article-content em  {{ font-style: italic; }}
        .article-content code {{ background: #f1f5f9; color: #2563eb; padding: 0.125rem 0.375rem; border-radius: 0.25rem; font-family: 'Courier New', monospace; font-size: 0.9em; }}
        .article-content blockquote {{ border-left: 4px solid #3b82f6; padding-left: 1.25rem; margin: 2rem 0; font-style: italic; color: #6b7280; }}

        /* Mobile menu */
        #mobile-menu {{ display: none; }}
        #mobile-menu.open {{ display: block; }}
    </style>
</head>
<body class="bg-[#f8f9fa] text-[#1a1a1a]">

    <!-- ── Top navigation bar ── -->
    <nav class="sticky top-0 z-[100] bg-white/90 backdrop-blur-xl border-b border-gray-100 shadow-sm">
        <div class="max-w-7xl mx-auto px-5 h-20 flex items-center justify-between gap-4">

            <!-- Logo -->
            <a href="{root}index.html" class="text-2xl font-extrabold tracking-tighter hover:text-blue-600 transition shrink-0">
                RAAPPO<span class="text-blue-600">.</span>
            </a>

            <!-- Desktop nav links -->
            <div class="hidden lg:flex items-center gap-8">
                <a href="{root}index.html" class="text-[11px] font-black uppercase tracking-[0.18em] text-gray-500 hover:text-blue-600 transition">Home</a>
                <a href="{root}index.html#trending" class="text-[11px] font-black uppercase tracking-[0.18em] text-gray-500 hover:text-blue-600 transition">Trending</a>
                <a href="{root}index.html#archive" class="text-[11px] font-black uppercase tracking-[0.18em] text-gray-500 hover:text-blue-600 transition">Archive</a>
                <a href="{root}index.html#about" class="text-[11px] font-black uppercase tracking-[0.18em] text-gray-500 hover:text-blue-600 transition">About</a>
            </div>

            <!-- Right controls -->
            <div class="flex items-center gap-3">
                <span class="hidden md:inline-flex text-[10px] font-bold text-emerald-600 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-full uppercase tracking-widest items-center gap-1.5">
                    <span class="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span> Live 2026
                </span>
                <!-- Hamburger button (mobile) -->
                <button
                    id="hamburger-btn"
                    class="lg:hidden w-10 h-10 flex flex-col items-center justify-center gap-[5px] rounded-xl border border-gray-200 hover:bg-gray-50 transition"
                    aria-label="Open menu"
                    onclick="document.getElementById('mobile-menu').classList.toggle('open')"
                >
                    <span class="w-5 h-[2px] bg-gray-700 rounded-full"></span>
                    <span class="w-5 h-[2px] bg-gray-700 rounded-full"></span>
                    <span class="w-5 h-[2px] bg-gray-700 rounded-full"></span>
                </button>
            </div>
        </div>

        <!-- Mobile dropdown menu -->
        <div id="mobile-menu" class="lg:hidden bg-white border-t border-gray-100 px-5 py-4">
            <ul class="flex flex-col gap-1">
                <li><a href="{root}index.html" class="flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-bold text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition">🏠 Home</a></li>
                <li><a href="{root}index.html#trending" class="flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-bold text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition">🔥 Trending</a></li>
                <li><a href="{root}index.html#archive" class="flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-bold text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition">📚 Archive</a></li>
                <li><a href="{root}index.html#about" class="flex items-center gap-2 px-4 py-3 rounded-xl text-sm font-bold text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition">ℹ️ About</a></li>
            </ul>
        </div>
    </nav>

    <!-- ── Page content ── -->
    <main class="max-w-7xl mx-auto px-5 py-12">
        {content}
    </main>

    <!-- ── Footer ── -->
    <footer class="bg-gray-900 text-gray-300 mt-24">
        <div class="max-w-7xl mx-auto px-5 pt-16 pb-10">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-12 mb-12">
                <div>
                    <div class="text-2xl font-black text-white tracking-tighter mb-4">RAAPPO<span class="text-blue-400">.</span></div>
                    <p class="text-gray-400 text-sm leading-relaxed">Decentralized autonomous news network delivering the most vital technological intelligence of 2026.</p>
                </div>
                <div>
                    <h4 class="font-bold uppercase tracking-widest text-xs text-gray-500 mb-5">Navigate</h4>
                    <ul class="space-y-3 text-sm font-medium">
                        <li><a href="{root}index.html" class="hover:text-white transition">Front Page</a></li>
                        <li><a href="{root}index.html#trending" class="hover:text-white transition">Trending</a></li>
                        <li><a href="{root}index.html#archive" class="hover:text-white transition">Archive</a></li>
                        <li><a href="{root}index.html#about" class="hover:text-white transition">About</a></li>
                    </ul>
                </div>
                <div>
                    <h4 class="font-bold uppercase tracking-widest text-xs text-gray-500 mb-5">System</h4>
                    <div class="flex items-center gap-2 text-sm text-emerald-400 font-bold mb-4">
                        <span class="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></span>
                        All systems operational
                    </div>
                    <p class="text-xs text-gray-600">Powered by Gemini 2.5 · Supabase · Cloudflare Pages</p>
                </div>
            </div>
            <div class="border-t border-gray-800 pt-8 flex flex-col md:flex-row justify-between items-center gap-4 text-xs text-gray-600">
                <p>© 2026 RAAPPO GLOBAL. All rights reserved.</p>
                <div class="flex gap-6 uppercase tracking-widest font-bold">
                    <a href="#" class="hover:text-gray-300 transition">Privacy</a>
                    <a href="#" class="hover:text-gray-300 transition">Terms</a>
                    <a href="#" class="hover:text-gray-300 transition">RSS</a>
                </div>
            </div>
        </div>
    </footer>

</body>
</html>"""

if __name__ == "__main__":
    generate_article()
