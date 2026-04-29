import os
import time
import re
import requests
from google import genai
from google.genai import types
from supabase import create_client

# ─────────────────────────────────────────────
# 1. Configuration & Setup
# ─────────────────────────────────────────────
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SB_URL     = os.environ.get("SUPABASE_URL")
SB_KEY     = os.environ.get("SUPABASE_KEY")

client   = genai.Client(api_key=GEMINI_KEY)
supabase = create_client(SB_URL, SB_KEY)

# ─────────────────────────────────────────────
# 2. Image Persistence Engine
# ─────────────────────────────────────────────
def download_and_store_image(keywords: str, post_id: int) -> str:
    """
    Downloads a topic-relevant image from Unsplash and stores it locally.
    Returns the relative asset path (assets/image_{post_id}.jpg).
    Falls back to picsum if Unsplash fails.
    """
    if not os.path.exists("assets"):
        os.makedirs("assets")

    local_path   = f"assets/image_{post_id}.jpg"
    safe_kw      = re.sub(r"[^a-zA-Z0-9,\s]", "", keywords)[:80].strip()
    unsplash_url = f"https://source.unsplash.com/featured/1600x900?{safe_kw},tech"
    fallback_url = f"https://picsum.photos/seed/raappopost{post_id}/1600/900"

    for url in (unsplash_url, fallback_url):
        try:
            r = requests.get(url, timeout=15, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 10_000:
                with open(local_path, "wb") as f:
                    f.write(r.content)
                return local_path
        except Exception:
            continue

    return fallback_url   # absolute URL as last-resort

def get_asset_url(post_id: int, root: str = "") -> str:
    """Return the best available image URL for a post."""
    local = f"assets/image_{post_id}.jpg"
    if os.path.exists(local):
        return f"{root}{local}"
    return f"https://picsum.photos/seed/raappopost{post_id}/1600/900"

# ─────────────────────────────────────────────
# 3. Supabase Helpers
# ─────────────────────────────────────────────
def get_next_available_id() -> int:
    result = supabase.table("content_farm").select("id").order("id", desc=False).execute()
    existing = {row["id"] for row in result.data}
    i = 1
    while i in existing:
        i += 1
    return i

# ─────────────────────────────────────────────
# 4. Markdown → HTML Converter
# ─────────────────────────────────────────────
def inline_markdown(text: str) -> str:
    text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*(.+?)\*\*",     r'<strong class="font-semibold text-gray-900">\1</strong>', text)
    text = re.sub(r"\*(.+?)\*",         r'<em class="italic">\1</em>', text)
    text = re.sub(r"`(.+?)`",           r'<code class="bg-gray-100 text-blue-700 px-1.5 py-0.5 rounded text-sm font-mono">\1</code>', text)
    return text

def markdown_to_html(text: str) -> str:
    lines        = text.split("\n")
    html_parts   = []
    in_ul        = False
    in_ol        = False
    in_para_lines = []

    def flush_para():
        nonlocal in_para_lines
        if in_para_lines:
            content = " ".join(in_para_lines).strip()
            if content:
                html_parts.append(
                    f'<p class="mb-8 text-gray-700 text-lg leading-relaxed">{inline_markdown(content)}</p>'
                )
            in_para_lines = []

    def close_list():
        nonlocal in_ul, in_ol
        if in_ul:
            html_parts.append("</ul>"); in_ul = False
        if in_ol:
            html_parts.append("</ol>"); in_ol = False

    for line in lines:
        stripped = line.rstrip()

        if stripped.startswith("```"):
            flush_para(); close_list(); continue

        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            flush_para(); close_list()
            level   = len(m.group(1))
            content = inline_markdown(m.group(2).strip())
            classes = {
                1: "text-3xl font-extrabold mt-14 mb-6 text-gray-900 border-b border-slate-100 pb-4",
                2: "text-3xl font-extrabold mt-14 mb-6 text-gray-900 border-b border-slate-100 pb-4",
                3: "text-2xl font-bold mt-10 mb-4 text-gray-900",
                4: "text-xl font-bold mt-8 mb-3 text-gray-800",
                5: "text-lg font-bold mt-6 mb-2 text-gray-800",
                6: "text-base font-bold mt-4 mb-2 text-gray-700",
            }
            cls = classes.get(level, classes[2])
            tag = "h2" if level <= 2 else f"h{level}"
            html_parts.append(f'<{tag} class="{cls}">{content}</{tag}>')
            continue

        m = re.match(r"^[\*\-]\s+(.*)", stripped)
        if m:
            flush_para()
            if in_ol: html_parts.append("</ol>"); in_ol = False
            if not in_ul:
                html_parts.append('<ul class="list-disc pl-6 mb-8 space-y-3 text-gray-700 text-lg leading-relaxed">')
                in_ul = True
            html_parts.append(f"<li>{inline_markdown(m.group(1))}</li>"); continue

        m = re.match(r"^\d+\.\s+(.*)", stripped)
        if m:
            flush_para()
            if in_ul: html_parts.append("</ul>"); in_ul = False
            if not in_ol:
                html_parts.append('<ol class="list-decimal pl-6 mb-8 space-y-3 text-gray-700 text-lg leading-relaxed">')
                in_ol = True
            html_parts.append(f"<li>{inline_markdown(m.group(1))}</li>"); continue

        if stripped == "":
            flush_para(); close_list(); continue

        in_para_lines.append(stripped)

    flush_para(); close_list()
    return "\n".join(html_parts)

def apply_html_styles(html_content: str) -> str:
    html_content = re.sub(r'<div\s+style="[^"]*">', "<div>", html_content)
    html_content = re.sub(r'<div\s+class="[^"]*">', "<div>", html_content)

    replacements = [
        (r"<h1(?![^>]*class)[^>]*>(.*?)</h1>",
         r'<h2 class="text-3xl font-extrabold mt-14 mb-6 text-gray-900 border-b border-slate-100 pb-4">\1</h2>'),
        (r"<h2(?![^>]*class)[^>]*>(.*?)</h2>",
         r'<h2 class="text-3xl font-extrabold mt-14 mb-6 text-gray-900 border-b border-slate-100 pb-4">\1</h2>'),
        (r"<h3(?![^>]*class)[^>]*>(.*?)</h3>",
         r'<h3 class="text-2xl font-bold mt-10 mb-4 text-gray-900">\1</h3>'),
        (r"<h4(?![^>]*class)[^>]*>(.*?)</h4>",
         r'<h4 class="text-xl font-bold mt-8 mb-3 text-gray-800">\1</h4>'),
        (r"<p(?![^>]*class)[^>]*>(.*?)</p>",
         r'<p class="mb-8 text-gray-700 text-lg leading-relaxed">\1</p>'),
        (r"<ul(?![^>]*class)[^>]*>",
         r'<ul class="list-disc pl-6 mb-8 space-y-3 text-gray-700 text-lg leading-relaxed">'),
        (r"<ol(?![^>]*class)[^>]*>",
         r'<ol class="list-decimal pl-6 mb-8 space-y-3 text-gray-700 text-lg leading-relaxed">'),
        (r"<li(?![^>]*class)[^>]*>",
         r'<li class="leading-relaxed">'),
        (r"<strong(?![^>]*class)[^>]*>(.*?)</strong>",
         r'<strong class="font-semibold text-gray-900">\1</strong>'),
    ]
    for pattern, repl in replacements:
        html_content = re.sub(pattern, repl, html_content, flags=re.DOTALL)

    html_content = re.sub(r"\*\*(.+?)\*\*",
                          r'<strong class="font-semibold text-gray-900">\1</strong>',
                          html_content)
    return html_content

def process_body_content(raw_content: str) -> str:
    text = raw_content.strip()

    if re.search(r"<html", text, re.IGNORECASE):
        body_match = re.search(r"<body[^>]*>(.*?)</body>", text, re.DOTALL | re.IGNORECASE)
        text = body_match.group(1).strip() if body_match else re.sub(
            r"</?html[^>]*>|<head>.*?</head>|</?body[^>]*>", "", text,
            flags=re.DOTALL | re.IGNORECASE).strip()

    if "BODY:" in text:
        after_body = text.split("BODY:", 1)[1]
        if "CONCLUSION:" in after_body:
            body_text, conclusion_text = after_body.split("CONCLUSION:", 1)
        else:
            body_text, conclusion_text = after_body, ""
        text = body_text.strip()
        if conclusion_text.strip():
            text += "\n\n## In Conclusion\n\n" + conclusion_text.strip()

    text = re.sub(r"^(TITLE|CATEGORY|SUMMARY|IMAGE_PROMPT):.*\n?", "", text, flags=re.MULTILINE).strip()

    if re.search(r"<(h[1-6]|ul|ol|blockquote|table)\b", text, re.IGNORECASE):
        return apply_html_styles(text)
    return markdown_to_html(text)

# ─────────────────────────────────────────────
# 5. HTML Template Engine
# ─────────────────────────────────────────────
def render_base_template(title: str, content: str, is_home: bool = True) -> str:
    root = "" if is_home else "../"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | RAAPPO Global Intelligence</title>
    <meta name="description" content="RAAPPO Global Intelligence — Daily technology briefings on 2026's most consequential breakthroughs.">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&family=Lora:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
    <style>
        :root {{
            --color-accent:  #2563eb;
            --color-accent2: #0ea5e9;
            --color-bg:      #f8f9fb;
            --color-surface: #ffffff;
            --color-text:    #1a1a2e;
            --radius-card:   1rem;
        }}

        *, *::before, *::after {{ box-sizing: border-box; }}
        html {{ scroll-behavior: smooth; }}
        body  {{ font-family: "Plus Jakarta Sans", sans-serif; background: var(--color-bg); color: var(--color-text); -webkit-font-smoothing: antialiased; }}

        /* ── Scrollbar ── */
        ::-webkit-scrollbar {{ width: 6px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: #cbd5e1; border-radius: 999px; }}

        /* ── Line clamp ── */
        .clamp-2 {{ display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
        .clamp-3 {{ display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}

        /* ── Article typography ── */
        .prose {{ font-family: "Lora", Georgia, serif; color: #374151; }}
        .prose p  {{ font-size: 1.125rem; line-height: 1.9; margin-bottom: 2rem; color: #374151; }}
        .prose h2 {{ font-family: "Plus Jakarta Sans", sans-serif; font-size: 1.65rem; font-weight: 800; color: #0f172a; margin-top: 3.5rem; margin-bottom: 1.25rem; padding-bottom: 0.75rem; border-bottom: 2px solid #f1f5f9; }}
        .prose h3 {{ font-family: "Plus Jakarta Sans", sans-serif; font-size: 1.3rem; font-weight: 700; color: #1e293b; margin-top: 2.5rem; margin-bottom: 0.9rem; }}
        .prose h4 {{ font-family: "Plus Jakarta Sans", sans-serif; font-size: 1.1rem; font-weight: 700; color: #374151; margin-top: 2rem; margin-bottom: 0.75rem; }}
        .prose ul {{ list-style: disc; padding-left: 1.75rem; margin-bottom: 2rem; }}
        .prose ol {{ list-style: decimal; padding-left: 1.75rem; margin-bottom: 2rem; }}
        .prose li {{ font-size: 1.05rem; line-height: 1.85; margin-bottom: 0.6rem; color: #374151; }}
        .prose strong {{ font-weight: 700; color: #111827; font-family: "Plus Jakarta Sans", sans-serif; }}
        .prose em    {{ font-style: italic; }}
        .prose code  {{ background: #f1f5f9; color: #2563eb; padding: 0.15rem 0.4rem; border-radius: 0.25rem; font-family: "Fira Code", monospace; font-size: 0.875em; }}
        .prose blockquote {{ border-left: 3px solid var(--color-accent); padding: 0.5rem 1.25rem; margin: 2.5rem 0; font-style: italic; color: #64748b; background: #f8fafc; border-radius: 0 0.5rem 0.5rem 0; }}

        /* ── Card hover ring ── */
        .card {{ transition: box-shadow 0.2s ease, transform 0.2s ease, border-color 0.2s ease; }}
        .card:hover {{ box-shadow: 0 8px 32px rgba(37,99,235,0.1); transform: translateY(-2px); border-color: #bfdbfe; }}

        /* ── Badge pill ── */
        .badge {{ display: inline-flex; align-items: center; gap: 0.3rem; font-size: 0.65rem; font-weight: 800; letter-spacing: 0.12em; text-transform: uppercase; padding: 0.25rem 0.65rem; border-radius: 999px; }}

        /* ── Mobile menu ── */
        #mobile-menu {{ display: none; }}
        #mobile-menu.open {{ display: block; }}

        /* ── Reading progress bar ── */
        #progress-bar {{
            position: fixed; top: 0; left: 0; height: 3px;
            background: linear-gradient(90deg, var(--color-accent), var(--color-accent2));
            width: 0%; z-index: 200; transition: width 0.1s linear;
        }}

        /* ── Fade-in on scroll ── */
        .reveal {{ opacity: 0; transform: translateY(18px); transition: opacity 0.5s ease, transform 0.5s ease; }}
        .reveal.visible {{ opacity: 1; transform: translateY(0); }}
    </style>
</head>
<body>
    <div id="progress-bar"></div>

    <!-- ── Navbar ── -->
    <nav class="sticky top-0 z-[100] bg-white/95 backdrop-blur-xl border-b border-gray-100 shadow-[0_1px_12px_rgba(0,0,0,0.06)]">
        <div class="max-w-6xl mx-auto px-5 h-16 flex items-center justify-between gap-4">

            <a href="{root}index.html" class="flex items-center gap-2 shrink-0 group">
                <span class="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center">
                    <span class="text-white text-xs font-black">R</span>
                </span>
                <span class="text-lg font-extrabold tracking-tight text-gray-900 group-hover:text-blue-600 transition">RAAPPO<span class="text-blue-600">.</span></span>
            </a>

            <div class="hidden lg:flex items-center gap-7">
                <a href="{root}index.html"           class="text-[11px] font-black uppercase tracking-[0.15em] text-gray-500 hover:text-blue-600 transition">Home</a>
                <a href="{root}index.html#latest"    class="text-[11px] font-black uppercase tracking-[0.15em] text-gray-500 hover:text-blue-600 transition">Latest</a>
                <a href="{root}index.html#archive"   class="text-[11px] font-black uppercase tracking-[0.15em] text-gray-500 hover:text-blue-600 transition">Archive</a>
                <a href="{root}index.html#about"     class="text-[11px] font-black uppercase tracking-[0.15em] text-gray-500 hover:text-blue-600 transition">About</a>
            </div>

            <div class="flex items-center gap-3">
                <span class="hidden sm:inline-flex badge bg-emerald-50 text-emerald-600 border border-emerald-200">
                    <span class="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse"></span>
                    Live 2026
                </span>
                <button id="hamburger-btn"
                    class="lg:hidden w-9 h-9 flex flex-col items-center justify-center gap-[5px] rounded-lg border border-gray-200 hover:bg-gray-50 transition"
                    aria-label="Open menu"
                    onclick="document.getElementById('mobile-menu').classList.toggle('open')">
                    <span class="w-4.5 h-[2px] bg-gray-700 rounded-full block w-5"></span>
                    <span class="w-4.5 h-[2px] bg-gray-700 rounded-full block w-5"></span>
                    <span class="w-4.5 h-[2px] bg-gray-700 rounded-full block w-5"></span>
                </button>
            </div>
        </div>

        <div id="mobile-menu" class="lg:hidden bg-white border-t border-gray-100 px-5 py-3">
            <ul class="flex flex-col gap-1">
                <li><a href="{root}index.html"         class="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition">🏠 Home</a></li>
                <li><a href="{root}index.html#latest"  class="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition">⚡ Latest</a></li>
                <li><a href="{root}index.html#archive" class="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition">📚 Archive</a></li>
                <li><a href="{root}index.html#about"   class="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-bold text-gray-700 hover:bg-blue-50 hover:text-blue-600 transition">ℹ️ About</a></li>
            </ul>
        </div>
    </nav>

    <!-- ── Page content ── -->
    <main class="max-w-6xl mx-auto px-5 py-10">
        {content}
    </main>

    <!-- ── Footer ── -->
    <footer class="bg-gray-950 text-gray-400 mt-20">
        <div class="max-w-6xl mx-auto px-5 pt-12 pb-8">
            <div class="grid grid-cols-1 md:grid-cols-3 gap-10 mb-10">
                <div>
                    <div class="flex items-center gap-2 mb-3">
                        <span class="w-6 h-6 rounded-md bg-blue-600 flex items-center justify-center">
                            <span class="text-white text-[10px] font-black">R</span>
                        </span>
                        <span class="text-base font-black text-white tracking-tight">RAAPPO<span class="text-blue-400">.</span></span>
                    </div>
                    <p class="text-gray-500 text-sm leading-relaxed">Daily technology intelligence — covering 2026's most consequential breakthroughs in AI, energy, materials, and computing.</p>
                </div>
                <div>
                    <h4 class="font-bold uppercase tracking-widest text-[10px] text-gray-600 mb-4">Navigate</h4>
                    <ul class="space-y-2.5 text-sm font-medium">
                        <li><a href="{root}index.html"         class="hover:text-white transition">Front Page</a></li>
                        <li><a href="{root}index.html#latest"  class="hover:text-white transition">Latest</a></li>
                        <li><a href="{root}index.html#archive" class="hover:text-white transition">Archive</a></li>
                        <li><a href="{root}index.html#about"   class="hover:text-white transition">About</a></li>
                    </ul>
                </div>
                <div>
                    <h4 class="font-bold uppercase tracking-widest text-[10px] text-gray-600 mb-4">System</h4>
                    <div class="flex items-center gap-2 text-sm text-emerald-400 font-semibold mb-3">
                        <span class="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></span>
                        All systems operational
                    </div>
                    <p class="text-xs text-gray-600">Powered by Gemini 2.5 · Supabase · Cloudflare Pages</p>
                </div>
            </div>
            <div class="border-t border-gray-900 pt-6 flex flex-col md:flex-row justify-between items-center gap-3 text-xs text-gray-600">
                <p>© 2026 RAAPPO Global Intelligence. All rights reserved.</p>
                <div class="flex gap-5 uppercase tracking-widest font-bold">
                    <a href="#" class="hover:text-gray-300 transition">Privacy</a>
                    <a href="#" class="hover:text-gray-300 transition">Terms</a>
                    <a href="#" class="hover:text-gray-300 transition">RSS</a>
                </div>
            </div>
        </div>
    </footer>

    <!-- ── Reading progress + scroll reveals ── -->
    <script>
        // Progress bar
        window.addEventListener("scroll", () => {{
            const el   = document.getElementById("progress-bar");
            const doc  = document.documentElement;
            const pct  = (doc.scrollTop / (doc.scrollHeight - doc.clientHeight)) * 100;
            if (el) el.style.width = pct + "%";
        }});

        // Reveal on scroll
        const revealEls = document.querySelectorAll(".reveal");
        const obs = new IntersectionObserver((entries) => {{
            entries.forEach(e => {{ if (e.isIntersecting) e.target.classList.add("visible"); }});
        }}, {{ threshold: 0.12 }});
        revealEls.forEach(el => obs.observe(el));
    </script>
</body>
</html>"""

# ─────────────────────────────────────────────
# 6. Post Page Renderer
# ─────────────────────────────────────────────
def render_post_page(post: dict, img_path: str) -> None:
    post_id    = post["id"]
    post_date  = post["created_at"][:10]
    post_title = post["title"]
    body_html  = process_body_content(post["body_content"])
    img_src    = get_asset_url(post_id, root="../")

    content = f"""
    <div class="max-w-3xl mx-auto">

        <!-- Breadcrumb -->
        <nav class="mb-8 text-sm font-medium text-gray-500 flex items-center gap-2 flex-wrap">
            <a href="../index.html" class="hover:text-blue-600 transition font-semibold">Home</a>
            <span class="text-gray-300">/</span>
            <span class="text-gray-700 truncate max-w-xs">{post_title}</span>
        </nav>

        <article>
            <!-- Header -->
            <header class="mb-10">
                <div class="flex flex-wrap items-center gap-3 mb-5">
                    <span class="badge bg-blue-600 text-white">Technical Analysis</span>
                    <span class="text-gray-400 text-sm">{post_date}</span>
                    <span class="text-gray-300">·</span>
                    <span class="text-gray-400 text-sm">5 min read</span>
                </div>
                <h1 class="text-3xl md:text-4xl font-extrabold leading-tight text-gray-900 mb-5 tracking-tight">{post_title}</h1>
            </header>

            <!-- Hero image -->
            <figure class="mb-12 rounded-2xl overflow-hidden shadow-lg">
                <img src="{img_src}"
                     alt="{post_title}"
                     class="w-full aspect-video object-cover"
                     loading="eager">
            </figure>

            <!-- Body -->
            <div class="prose">
                {body_html}
            </div>

            <!-- Footer -->
            <footer class="mt-14 pt-7 border-t border-gray-100 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                <a href="../index.html"
                   class="inline-flex items-center gap-2 text-blue-600 font-bold hover:gap-3 transition-all text-sm">
                    ← Back to all articles
                </a>
                <span class="text-xs text-gray-400 uppercase tracking-widest font-bold">RAAPPO · Global Intelligence</span>
            </footer>
        </article>
    </div>
    """

    with open(f"posts/post_{post_id}.html", "w", encoding="utf-8") as f:
        f.write(render_base_template(post_title, content, is_home=False))

# ─────────────────────────────────────────────
# 7. Homepage Builder
# ─────────────────────────────────────────────
def build_homepage(all_posts: list, hero_summary: str, target_id: int) -> None:
    if not all_posts:
        return

    hero = all_posts[0]
    hero_img = get_asset_url(hero["id"])

    # ── Featured hero (compact, editorial) ──────────────────────────
    hero_html = f"""
    <section id="latest" class="mb-16 reveal">
        <div class="relative rounded-2xl overflow-hidden bg-gray-900 h-[380px] md:h-[440px] flex items-end">
            <img src="{hero_img}"
                 alt="{hero["title"]}"
                 class="absolute inset-0 w-full h-full object-cover opacity-30">
            <div class="absolute inset-0 bg-gradient-to-t from-gray-950 via-gray-900/60 to-transparent"></div>
            <div class="relative z-10 p-7 md:p-12 max-w-2xl">
                <div class="flex flex-wrap items-center gap-2 mb-4">
                    <span class="badge bg-blue-600 text-white">Featured</span>
                    <span class="text-gray-400 text-xs font-medium">{hero["created_at"][:10]}</span>
                </div>
                <h2 class="text-2xl md:text-4xl font-extrabold text-white mb-4 leading-tight tracking-tight clamp-3">{hero["title"]}</h2>
                <p class="text-gray-300 text-sm md:text-base mb-6 leading-relaxed clamp-2">{hero_summary}</p>
                <a href="posts/post_{hero["id"]}.html"
                   class="inline-flex items-center gap-2 bg-white text-gray-900 px-6 py-2.5 rounded-full font-bold text-sm hover:bg-blue-600 hover:text-white transition-all group">
                    Read Full Report
                    <span class="group-hover:translate-x-1 transition-transform">→</span>
                </a>
            </div>
        </div>
    </section>
    """

    # ── Article cards grid ────────────────────────────────────────
    cards_html = ""
    category_colors = {
        "Breaking": "bg-red-50 text-red-600",
        "Deep Dive": "bg-blue-50 text-blue-600",
        "Analysis": "bg-amber-50 text-amber-700",
        "Technical Analysis": "bg-purple-50 text-purple-600",
    }

    for post in all_posts:
        p_id    = post["id"]
        p_title = post["title"]
        p_date  = post["created_at"][:10]
        thumb   = get_asset_url(p_id)
        cat     = "Breaking"
        cat_cls = category_colors.get(cat, "bg-blue-50 text-blue-600")

        cards_html += f"""
        <a href="posts/post_{p_id}.html"
           class="card group block bg-white border border-gray-100 rounded-2xl overflow-hidden">
            <div class="aspect-video bg-gray-100 overflow-hidden">
                <img src="{thumb}"
                     alt="{p_title}"
                     loading="lazy"
                     class="w-full h-full object-cover group-hover:scale-[1.03] transition-transform duration-500">
            </div>
            <div class="p-5">
                <div class="flex items-center gap-2 mb-2.5">
                    <span class="badge {cat_cls}">{cat}</span>
                    <span class="text-gray-400 text-[11px] font-medium">{p_date}</span>
                </div>
                <h3 class="text-base font-bold text-gray-900 group-hover:text-blue-600 clamp-2 leading-snug mb-2">{p_title}</h3>
                <span class="text-xs text-blue-600 font-bold flex items-center gap-1 group-hover:gap-2 transition-all mt-3">
                    Read more <span>→</span>
                </span>
            </div>
        </a>
        """

    # ── Latest strip (top 3, horizontal compact) ─────────────────
    strip_html = ""
    for post in all_posts[1:4]:
        strip_img = get_asset_url(post["id"])
        strip_html += f"""
        <a href="posts/post_{post["id"]}.html"
           class="card group flex gap-4 bg-white border border-gray-100 rounded-xl p-4 items-start">
            <div class="w-20 h-20 rounded-lg overflow-hidden shrink-0 bg-gray-100">
                <img src="{strip_img}" alt="{post["title"]}" loading="lazy"
                     class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300">
            </div>
            <div class="min-w-0">
                <span class="text-[10px] font-black text-gray-400 uppercase tracking-widest">{post["created_at"][:10]}</span>
                <h4 class="text-sm font-bold text-gray-900 group-hover:text-blue-600 clamp-2 leading-snug mt-1">{post["title"]}</h4>
            </div>
        </a>
        """

    content = f"""
    {hero_html}

    <!-- Section: Recent strip -->
    <section class="mb-14 reveal">
        <div class="flex items-center gap-4 mb-5">
            <h2 class="text-base font-extrabold uppercase tracking-widest text-gray-500 whitespace-nowrap">Recent</h2>
            <div class="h-px flex-grow bg-gray-100"></div>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            {strip_html}
        </div>
    </section>

    <!-- Section: All articles grid -->
    <section id="archive" class="mb-16 reveal">
        <div class="flex items-center gap-4 mb-7">
            <h2 class="text-xl font-extrabold tracking-tight whitespace-nowrap">
                Latest <span class="text-blue-600">Intelligence</span>
            </h2>
            <div class="h-px flex-grow bg-gray-100"></div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {cards_html}
        </div>
    </section>

    <!-- About -->
    <section id="about" class="bg-white rounded-2xl p-8 md:p-12 border border-gray-100 shadow-sm reveal">
        <div class="max-w-xl">
            <span class="badge bg-blue-50 text-blue-600 mb-4 inline-block">About RAAPPO</span>
            <h2 class="text-2xl font-extrabold text-gray-900 mb-4 leading-tight">Global Intelligence for 2026</h2>
            <p class="text-gray-600 leading-relaxed mb-3">RAAPPO is a decentralized, AI-augmented news platform synthesising real-time technological breakthroughs into long-form, investigative journalism — published daily.</p>
            <p class="text-gray-500 text-sm leading-relaxed">Powered by Gemini 2.5 Flash with Google Search grounding · Supabase · Cloudflare Pages.</p>
        </div>
    </section>
    """

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(render_base_template("RAAPPO — Global Intelligence 2026", content, is_home=True))

# ─────────────────────────────────────────────
# 8. Main Orchestrator
# ─────────────────────────────────────────────
def generate_article() -> None:
    model_id  = "gemini-2.5-flash"
    target_id = get_next_available_id()

    prompt = """
Write a professional, in-depth technology news article dated today in 2026.
Do NOT mention that this is AI-generated or automated. Write as a human journalist.

Return ONLY in this exact format with no extra commentary:
TITLE: [Concise, factual, compelling title — no clickbait]
CATEGORY: [Breaking, Deep Dive, or Analysis]
SUMMARY: [Professional 2-sentence summary for the homepage]
IMAGE_PROMPT: [3 comma-separated keywords for a relevant tech image, e.g. solar,panel,efficiency]
BODY:
[1200 words of formatted markdown. Use ## for H2 headers. Use ### for H3 headers.
Use **bold** for emphasis. Use bullet lists with - prefix.
Write substantive paragraphs separated by blank lines.
Avoid hollow filler sentences — every sentence must add information or insight.]
CONCLUSION:
[2-3 sentences of forward-looking final thoughts]
"""

    response = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )
            break
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {e}")
            time.sleep(20)

    if not response:
        print("All generation attempts failed.")
        return

    text = response.text

    # Parse metadata
    try:
        title     = re.search(r"TITLE:\s*(.*)",        text).group(1).strip()
        category  = re.search(r"CATEGORY:\s*(.*)",     text).group(1).strip()
        summary   = re.search(r"SUMMARY:\s*(.*)",      text).group(1).strip()
        img_kw    = re.search(r"IMAGE_PROMPT:\s*(.*)", text).group(1).strip()
    except Exception:
        title, category, summary, img_kw = (
            "Tech Intelligence 2026", "Breaking",
            "The latest in global technology.", "technology,innovation,2026"
        )

    # Download & store image
    img_path = download_and_store_image(img_kw, target_id)

    # Persist to Supabase
    supabase.table("content_farm").insert({
        "id":          target_id,
        "title":       title,
        "body_content": text,
        "domain_name": "news.raappo.cf",
    }).execute()

    # Fetch all posts and rebuild site
    if not os.path.exists("posts"):
        os.makedirs("posts")

    all_posts = (
        supabase.table("content_farm")
        .select("*")
        .order("created_at", desc=True)
        .execute()
        .data
    )

    # Render individual post pages
    for post in all_posts:
        render_post_page(post, get_asset_url(post["id"]))

    # Rebuild homepage
    build_homepage(all_posts, summary, target_id)

    print(f"✓ Published post {target_id}: {title}")
    print(f"✓ Image stored at: {img_path}")


if __name__ == "__main__":
    generate_article()
