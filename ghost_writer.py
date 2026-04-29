import os
import time
import re
import requests
import urllib.parse
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
    # Unsplash source API is deprecated, using pollinations.ai for AI-generated tech images
    pollinations_url = f"https://image.pollinations.ai/prompt/technological%20{encoded_kw}?width=1600&height=900&nologo=true"
    fallback_url = f"https://placehold.co/1600x900/171717/38bdf8?text=Intelligence+Report"

    for url in (pollinations_url, fallback_url):
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
    return f"https://placehold.co/1600x900/171717/38bdf8?text=Intelligence+Report"

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
<html lang="en" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} | RAAPPO Global Intelligence</title>
    <meta name="description" content="RAAPPO Global Intelligence — Daily technology briefings on 2026's most consequential breakthroughs.">
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {{
        darkMode: 'class',
        theme: {{
          extend: {{
            colors: {{
              brand: {{
                400: '#38bdf8',
                500: '#0ea5e9',
                600: '#0284c7',
              }},
              dark: {{
                900: '#0a0a0a',
                800: '#171717',
                700: '#262626',
              }}
            }},
            fontFamily: {{
              sans: ['"Plus Jakarta Sans"', 'sans-serif'],
              serif: ['"Lora"', 'serif'],
              mono: ['"Fira Code"', 'monospace'],
            }}
          }}
        }}
      }}
    </script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:ital,wght@0,400;0,500;0,600;0,700;0,800;1,400&family=Lora:ital,wght@0,400;0,500;0,600;1,400&display=swap" rel="stylesheet">
    <style>
        body {{
            background-color: #0a0a0a;
            color: #e5e5e5;
            -webkit-font-smoothing: antialiased;
            overflow-x: hidden;
        }}
        
        ::selection {{ background: rgba(14, 165, 233, 0.3); color: #fff; }}
        ::-webkit-scrollbar {{ width: 8px; }}
        ::-webkit-scrollbar-track {{ background: #0a0a0a; }}
        ::-webkit-scrollbar-thumb {{ background: #262626; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #404040; }}

        /* Background Glow Orb */
        .glow-orb {{
            position: absolute;
            top: -200px;
            left: 50%;
            transform: translateX(-50%);
            width: 800px;
            height: 400px;
            background: radial-gradient(ellipse at center, rgba(14,165,233,0.15) 0%, rgba(10,10,10,0) 70%);
            pointer-events: none;
            z-index: -1;
        }}

        .clamp-2 {{ display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
        .clamp-3 {{ display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }}

        /* Glass Nav */
        .glass-nav {{
            background: rgba(10, 10, 10, 0.65);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }}

        /* Typography tweaks */
        .prose {{ font-family: "Lora", serif; font-size: 1.05rem; line-height: 1.8; color: #ffffff; }}
        .prose p {{ margin-bottom: 2rem; }}
        .prose h2 {{ font-family: "Plus Jakarta Sans", sans-serif; font-size: 1.8rem; font-weight: 800; color: #ffffff; margin-top: 4rem; margin-bottom: 1.5rem; letter-spacing: -0.02em; border-bottom: 1px solid #262626; padding-bottom: 0.5rem; }}
        .prose h3 {{ font-family: "Plus Jakarta Sans", sans-serif; font-size: 1.4rem; font-weight: 700; color: #f4f4f5; margin-top: 3rem; margin-bottom: 1rem; }}
        .prose h4 {{ font-family: "Plus Jakarta Sans", sans-serif; font-size: 1.2rem; font-weight: 700; color: #f4f4f5; margin-top: 2rem; margin-bottom: 0.75rem; }}
        .prose ul, .prose ol {{ margin-bottom: 2rem; padding-left: 1.5rem; }}
        .prose li {{ margin-bottom: 0.75rem; }}
        .prose strong {{ color: #ffffff; font-weight: 600; font-family: "Plus Jakarta Sans", sans-serif; }}
        .prose a {{ color: #38bdf8; text-decoration: none; border-bottom: 1px solid rgba(56,189,248,0.3); transition: border-color 0.2s; }}
        .prose a:hover {{ border-color: rgba(56,189,248,1); }}
        .prose blockquote {{ border-left: 3px solid #0ea5e9; padding: 1rem 1.5rem; font-style: italic; color: #a1a1aa; margin: 2.5rem 0; background: #171717; border-radius: 0 0.5rem 0.5rem 0; }}
        .prose code {{ background: #171717; color: #38bdf8; padding: 0.2rem 0.4rem; border-radius: 0.25rem; font-family: "Fira Code", monospace; font-size: 0.85em; border: 1px solid #262626; }}

        /* Premium Cards */
        .card-premium {{
            background: rgba(23, 23, 23, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
        }}
        .card-premium:hover {{
            transform: translateY(-4px);
            background: rgba(23, 23, 23, 0.8);
            border-color: rgba(14, 165, 233, 0.3);
            box-shadow: 0 20px 40px -10px rgba(0, 0, 0, 0.5), 0 0 20px rgba(14, 165, 233, 0.1);
        }}

        /* Badges */
        .badge {{
            font-size: 0.7rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase;
            padding: 0.25rem 0.75rem; border-radius: 999px;
            background: rgba(14, 165, 233, 0.1);
            color: #38bdf8;
            border: 1px solid rgba(14, 165, 233, 0.2);
            display: inline-flex; align-items: center; gap: 0.3rem;
        }}
        .badge-pulse {{ position: relative; padding-left: 1.75rem; }}
        .badge-pulse::before {{
            content: ''; position: absolute; left: 0.6rem; top: 50%; transform: translateY(-50%);
            width: 6px; height: 6px; border-radius: 50%; background: #38bdf8;
            box-shadow: 0 0 8px #38bdf8; animation: pulse 2s infinite;
        }}

        @keyframes pulse {{
            0% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(56,189,248, 0.4); }}
            70% {{ opacity: 0.5; box-shadow: 0 0 0 4px rgba(56,189,248, 0); }}
            100% {{ opacity: 1; box-shadow: 0 0 0 0 rgba(56,189,248, 0); }}
        }}

        #progress-bar {{
            position: fixed; top: 0; left: 0; height: 2px;
            background: #0ea5e9;
            box-shadow: 0 0 10px #0ea5e9;
            width: 0%; z-index: 200; transition: width 0.1s;
        }}
    </style>
</head>
<body class="antialiased relative">
    <div class="glow-orb"></div>
    <div id="progress-bar"></div>

    <!-- ── Navbar ── -->
    <nav class="sticky top-0 z-[100] glass-nav transition-all duration-300" id="navbar">
        <div class="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
            <a href="{root}index.html" class="flex items-center gap-3 group">
                <div class="w-8 h-8 rounded bg-gradient-to-br from-brand-400 to-brand-600 flex items-center justify-center shadow-[0_0_15px_rgba(14,165,233,0.3)] group-hover:shadow-[0_0_20px_rgba(14,165,233,0.5)] transition-all duration-300">
                    <span class="text-white text-sm font-black tracking-tighter">R</span>
                </div>
                <span class="text-lg font-extrabold tracking-tight text-white group-hover:text-brand-400 transition-colors">RAAPPO<span class="text-brand-500">.</span></span>
            </a>

            <div class="hidden md:flex items-center gap-8">
                <a href="{root}index.html"           class="text-[11px] font-bold uppercase tracking-[0.2em] text-neutral-400 hover:text-white transition-colors">Intelligence</a>
                <a href="{root}index.html#archive"   class="text-[11px] font-bold uppercase tracking-[0.2em] text-neutral-400 hover:text-white transition-colors">Archive</a>
            </div>

            <div class="flex items-center gap-4">
                <span class="hidden sm:inline-flex badge badge-pulse">Live 2026</span>
                <button id="hamburger-btn" class="md:hidden text-neutral-300 hover:text-white" aria-label="Open menu" onclick="document.getElementById('mobile-menu').classList.toggle('hidden')">
                    <span class="block w-5 h-[2px] bg-white mb-1"></span>
                    <span class="block w-5 h-[2px] bg-white mb-1"></span>
                    <span class="block w-5 h-[2px] bg-white"></span>
                </button>
            </div>
        </div>
        <div id="mobile-menu" class="hidden md:hidden bg-dark-900 border-b border-neutral-800 px-6 py-4 absolute w-full">
            <ul class="flex flex-col gap-4">
                <li><a href="{root}index.html" class="text-sm font-bold uppercase tracking-widest text-neutral-300 hover:text-brand-400">Intelligence</a></li>
                <li><a href="{root}index.html#archive" class="text-sm font-bold uppercase tracking-widest text-neutral-300 hover:text-brand-400">Archive</a></li>
            </ul>
        </div>
    </nav>

    <!-- ── Page content ── -->
    <main class="relative z-10 pt-10 pb-20">
        {content}
    </main>

    <!-- ── Footer ── -->
    <footer class="border-t border-neutral-800 bg-dark-900/50 mt-20">
        <div class="max-w-6xl mx-auto px-6 py-12 md:py-16">
            <div class="grid grid-cols-1 md:grid-cols-12 gap-10 md:gap-6">
                <div class="md:col-span-5">
                    <div class="flex items-center gap-3 mb-6">
                        <div class="w-6 h-6 rounded bg-brand-500 flex items-center justify-center">
                            <span class="text-white text-[10px] font-black">R</span>
                        </div>
                        <span class="text-lg font-black text-white tracking-tight">RAAPPO Global Intelligence</span>
                    </div>
                    <p class="text-neutral-400 text-sm leading-relaxed max-w-sm">Decentralized, AI-augmented intelligence briefings covering 2026's most consequential breakthroughs in quantum computing, AGI, and synthetic biology.</p>
                </div>
                <div class="md:col-span-3">
                    <h4 class="font-bold uppercase tracking-[0.2em] text-[10px] text-neutral-500 mb-5">Navigation</h4>
                    <ul class="space-y-3 text-sm text-neutral-400">
                        <li><a href="{root}index.html" class="hover:text-brand-400 transition-colors">Front Page</a></li>
                        <li><a href="{root}index.html#archive" class="hover:text-brand-400 transition-colors">Archives</a></li>
                    </ul>
                </div>
                <div class="md:col-span-4">
                    <h4 class="font-bold uppercase tracking-[0.2em] text-[10px] text-neutral-500 mb-5">System Status</h4>
                    <div class="bg-dark-800/50 rounded-lg p-4 border border-neutral-800/80 inline-block w-full">
                        <div class="flex items-center gap-3 mb-2">
                            <span class="w-2 h-2 bg-emerald-400 rounded-full animate-pulse"></span>
                            <span class="text-sm text-emerald-400 font-bold tracking-wide">Network Nominal</span>
                        </div>
                        <div class="text-[11px] text-neutral-500 uppercase tracking-wider font-mono">
                            Node: eu-central-1<br>
                            Status: Secure
                        </div>
                    </div>
                </div>
            </div>
            <div class="border-t border-neutral-800/80 mt-12 pt-8 flex flex-col md:flex-row justify-between items-center gap-4 text-[11px] text-neutral-500 uppercase tracking-widest font-semibold">
                <p>© 2026 RAAPPO. All rights reserved.</p>
                <div class="flex gap-6">
                    <a href="#" class="hover:text-brand-400 transition-colors">Privacy</a>
                    <a href="#" class="hover:text-brand-400 transition-colors">Terms</a>
                    <a href="#" class="hover:text-brand-400 transition-colors">Data Policy</a>
                </div>
            </div>
        </div>
    </footer>

    <script>
        // Progress bar
        window.addEventListener("scroll", () => {{
            const el = document.getElementById("progress-bar");
            const doc = document.documentElement;
            const pct = (doc.scrollTop / (doc.scrollHeight - doc.clientHeight)) * 100;
            if (el) el.style.width = pct + "%";
        }});
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
    <div class="max-w-3xl mx-auto px-5">
        <!-- Breadcrumb -->
        <nav class="mb-10 text-[11px] font-bold uppercase tracking-widest text-neutral-500 flex items-center gap-3 flex-wrap">
            <a href="../index.html" class="hover:text-brand-400 transition-colors">Intelligence</a>
            <span class="text-neutral-700">/</span>
            <span class="text-neutral-300 truncate max-w-xs">{post_title}</span>
        </nav>

        <article>
            <!-- Header -->
            <header class="mb-10">
                <div class="flex flex-wrap items-center gap-4 mb-4">
                    <span class="badge">Classified Report</span>
                    <span class="text-neutral-300 text-xs font-mono tracking-wider">{post_date}</span>
                </div>
                <h1 class="text-3xl md:text-4xl font-extrabold leading-[1.15] text-white mb-6 tracking-tight drop-shadow-sm">{post_title}</h1>
            </header>

            <!-- Hero image -->
            <figure class="mb-10 rounded-2xl overflow-hidden shadow-[0_0_40px_rgba(0,0,0,0.5)] border border-neutral-800 relative group">
                <div class="absolute inset-0 bg-gradient-to-t from-dark-900/60 via-transparent to-transparent z-10 pointer-events-none"></div>
                <img src="{img_src}"
                     alt="{post_title}"
                     class="w-full h-auto max-h-[400px] object-cover group-hover:scale-105 transition-transform duration-1000 ease-out"
                     loading="eager">
            </figure>

            <!-- Body -->
            <div class="prose">
                {body_html}
            </div>

            <!-- Footer -->
            <footer class="mt-20 pt-8 border-t border-neutral-800 flex flex-col sm:flex-row items-center justify-between gap-6">
                <a href="../index.html"
                   class="inline-flex items-center gap-2 bg-dark-800 hover:bg-dark-700 border border-neutral-700 text-white px-6 py-3 rounded-full font-bold text-sm transition-all group">
                    <span class="group-hover:-translate-x-1 transition-transform">←</span>
                    Return to Feed
                </a>
                <span class="text-[10px] text-neutral-600 uppercase tracking-[0.2em] font-bold">End of Report</span>
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

    # ── Featured hero ──────────────────────────
    hero_html = f"""
    <section class="mb-16 px-5">
        <div class="relative rounded-[1.5rem] overflow-hidden bg-dark-900 h-[320px] md:h-[400px] flex items-end shadow-[0_20px_50px_rgba(0,0,0,0.5)] border border-neutral-800 group cursor-pointer" onclick="window.location.href='posts/post_{hero["id"]}.html'">
            <img src="{hero_img}"
                 alt="{hero["title"]}"
                 class="absolute inset-0 w-full h-full object-cover opacity-50 group-hover:opacity-60 group-hover:scale-[1.03] transition-all duration-1000 ease-out">
            <div class="absolute inset-0 bg-gradient-to-t from-dark-900 via-dark-900/60 to-transparent pointer-events-none"></div>
            <div class="relative z-10 p-8 md:p-14 max-w-4xl">
                <div class="flex flex-wrap items-center gap-3 mb-4">
                    <span class="badge badge-pulse">Top Story</span>
                    <span class="text-brand-400 text-xs font-mono tracking-wider">{hero["created_at"][:10]}</span>
                </div>
                <h2 class="text-2xl md:text-4xl font-extrabold text-white mb-4 leading-[1.15] tracking-tight clamp-2 drop-shadow-md">{hero["title"]}</h2>
                <p class="text-neutral-300 text-sm md:text-base mb-6 leading-relaxed clamp-2 max-w-2xl drop-shadow">{hero_summary}</p>
                <div class="inline-flex items-center gap-3 bg-white text-dark-900 px-6 py-2.5 rounded-full font-bold text-sm hover:bg-brand-400 hover:text-white transition-all duration-300 group/btn">
                    Read Intelligence Report
                    <span class="group-hover/btn:translate-x-1 transition-transform">→</span>
                </div>
            </div>
        </div>
    </section>
    """

    # ── Article cards grid ────────────────────────────────────────
    cards_html = ""
    for post in all_posts:
        p_id    = post["id"]
        p_title = post["title"]
        p_date  = post["created_at"][:10]
        thumb   = get_asset_url(p_id)
        
        cards_html += f"""
        <a href="posts/post_{p_id}.html" class="card-premium group block rounded-xl overflow-hidden flex flex-col relative h-[280px]">
            <div class="h-36 overflow-hidden relative shrink-0">
                <div class="absolute inset-0 bg-dark-900/20 group-hover:bg-transparent transition-colors z-10"></div>
                <img src="{thumb}" alt="{p_title}" loading="lazy" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 ease-out">
            </div>
            <div class="p-5 flex flex-col flex-grow bg-dark-800/30">
                <div class="flex items-center gap-2 mb-3">
                    <span class="w-1.5 h-1.5 bg-brand-500 rounded-full"></span>
                    <span class="text-neutral-400 text-[10px] font-mono tracking-widest">{p_date}</span>
                </div>
                <h3 class="text-base font-bold text-white group-hover:text-brand-400 clamp-2 leading-snug mb-3 transition-colors">{p_title}</h3>
                <div class="mt-auto pt-3 border-t border-neutral-800/50 flex items-center justify-between">
                    <span class="text-[11px] text-neutral-300 font-bold uppercase tracking-widest group-hover:text-white transition-colors">Access File</span>
                    <span class="text-neutral-500 group-hover:text-brand-400 transition-colors group-hover:translate-x-1">→</span>
                </div>
            </div>
        </a>
        """

    content = f"""
    {hero_html}

    <!-- Section: Archive -->
    <section id="archive" class="mb-24 px-5">
        <div class="flex items-center gap-6 mb-10">
            <h2 class="text-2xl font-black tracking-tight text-white uppercase">Intelligence <span class="text-brand-500">Archive</span></h2>
            <div class="h-px flex-grow bg-gradient-to-r from-neutral-800 to-transparent"></div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8">
            {cards_html}
        </div>
    </section>
    """

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(render_base_template("Intelligence Feed", content, is_home=True))

def rebuild_site() -> None:
    import os
    if not os.path.exists("posts"):
        os.makedirs("posts")

    all_posts = (
        supabase.table("content_farm")
        .select("*")
        .order("created_at", desc=True)
        .execute()
        .data
    )
    
    if not all_posts:
        print("No posts found in database.")
        return

    # Render individual post pages
    for post in all_posts:
        render_post_page(post, get_asset_url(post["id"]))

    hero = all_posts[0]
    # Extract summary from body
    body = hero.get("body_content", "")
    summary = "Latest intelligence briefing."
    if "SUMMARY:" in body:
        try:
            summary = body.split("SUMMARY:")[1].split("IMAGE_PROMPT:")[0].strip()
        except:
            pass
    elif body:
        text = re.sub(r'<[^>]+>', '', body)
        text = re.sub(r'#.*', '', text)
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        if paragraphs:
            summary = paragraphs[0][:200] + "..."
            
    build_homepage(all_posts, summary, hero["id"])
    print("Site rebuilt successfully.")

def generate_article() -> None:
    target_id = get_next_available_id()

    prompt = """
Write a professional, in-depth technology news article dated today in 2026.
CRITICAL: Do NOT mention that this is AI-generated, automated, or written by an AI. Write as a human journalist. Do NOT use phrases like "As an AI", "I am a bot", or refer to your own generation process.

Return ONLY in this exact format with no extra commentary:
TITLE: [Concise, factual, compelling title — no clickbait]
CATEGORY: [Breaking, Deep Dive, or Analysis]
SUMMARY: [Professional 2-sentence summary for the homepage]
IMAGE_PROMPT: [3 comma-separated keywords for a relevant tech image, e.g. quantum,computing,processor]
BODY:
[1200 words of formatted markdown. Use ## for H2 headers. Use ### for H3 headers.
Use **bold** for emphasis. Use bullet lists with - prefix.
Write substantive paragraphs separated by blank lines.
Avoid hollow filler sentences — every sentence must add information or insight.]
CONCLUSION:
[2-3 sentences of forward-looking final thoughts]
"""

    response = None
    models_to_try = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash", "gemini-2.0-flash-lite-001", "gemini-1.5-flash"]
    
    for model_id in models_to_try:
        print(f"Trying generation with model: {model_id}")
        try:
            response = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )
            if response and response.text:
                print(f"Generation successful with {model_id}.")
                break
        except Exception as e:
            print(f"Model {model_id} failed: {e}")
            time.sleep(5)

    if not response or not response.text:
        print("All generation attempts failed. Rebuilding site with existing posts.")
        rebuild_site()
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

    print(f"Metadata extracted: {title} | {img_kw}")

    # Download & store image
    try:
        img_path = download_and_store_image(img_kw, target_id)
        print(f"✓ Image stored at: {img_path}")
    except Exception as e:
        print(f"Failed to download image: {e}")
        img_path = f"https://picsum.photos/seed/raappopost{target_id}/1600/900"

    # Persist to Supabase
    try:
        supabase.table("content_farm").insert({
            "id":          target_id,
            "title":       title,
            "body_content": text,
            "domain_name": "news.raappo.cf",
        }).execute()
        print(f"✓ Published post {target_id} to database.")
    except Exception as e:
        print(f"Failed to insert into Supabase: {e}")
        print("Rebuilding site with existing posts instead.")
        rebuild_site()
        return

    rebuild_site()

if __name__ == "__main__":
    generate_article()
