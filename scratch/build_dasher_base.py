import os
import re
import shutil

dasher_src = r"c:\Users\Aseel\Desktop\ai_sales_agent\dasher-1.0.0\src"
project_root = r"c:\Users\Aseel\Desktop\ai_sales_agent"
static_dir = os.path.join(project_root, "static", "dasher")

# ─── 1. Copy CSS + JS assets ───────────────────────────────────────────────────
os.makedirs(static_dir, exist_ok=True)

# Copy theme.css
css_src = os.path.join(dasher_src, "assets", "css", "theme.css")
css_dst_dir = os.path.join(static_dir, "css")
os.makedirs(css_dst_dir, exist_ok=True)
shutil.copy2(css_src, os.path.join(css_dst_dir, "theme.css"))
print("Copied theme.css")

# Copy JS assets
js_src_dir = os.path.join(dasher_src, "assets", "js")
js_dst_dir = os.path.join(static_dir, "js")
if os.path.exists(js_src_dir):
    shutil.copytree(js_src_dir, js_dst_dir, dirs_exist_ok=True)
    print("Copied JS assets")

# Copy images
img_src_dir = os.path.join(dasher_src, "assets", "images")
img_dst_dir = os.path.join(static_dir, "images")
if os.path.exists(img_src_dir):
    shutil.copytree(img_src_dir, img_dst_dir, dirs_exist_ok=True)
    print("Copied images")

# ─── 2. Read and resolve partials in index.html ───────────────────────────────
with open(os.path.join(dasher_src, "index.html"), "r", encoding="utf-8") as f:
    content = f.read()

def resolve_includes(html, base_dir):
    pattern = r'@@include\("([^"]+)"\)'
    for _ in range(10):  # up to 10 levels deep
        def replacer(m):
            rel = m.group(1)
            full = os.path.join(base_dir, rel)
            if os.path.exists(full):
                with open(full, "r", encoding="utf-8") as f2:
                    return f2.read()
            return ""
        content_new = re.sub(pattern, replacer, html)
        if content_new == html:
            break
        html = content_new
    return html

content = resolve_includes(content, dasher_src)

# Replace @@webRoot with /static/dasher
content = content.replace("@@webRoot", "/static/dasher")

# ─── 3. Write a "resolved" index for reference ────────────────────────────────
out_path = os.path.join(project_root, "scratch", "dasher_resolved.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(content)
print(f"Written resolved HTML to: {out_path}")

# ─── 4. Extract sidebar, topbar, and scripts blocks ─────────────────────────
# Find miniSidebar block
sidebar_start = content.find('<div id="miniSidebar">')
sidebar_end = content.find('<!-- Main Content -->')
sidebar_html = content[sidebar_start:sidebar_end].strip() if sidebar_start != -1 else ""

# Find offcanvasNav block (mobile sidebar)
offcanvas_start = content.find('<div class="offcanvasNav')
offcanvas_end = content.find('<!-- Main Content -->')
offcanvas_html = content[offcanvas_start:offcanvas_end].strip() if offcanvas_start != -1 else ""

# Find topbar
topbar_start = content.find('id="topbar"')
if topbar_start == -1:
    topbar_start = content.find('class="topbar')
topbar_end = content.find('<!-- container -->')
topbar_html = content[topbar_start:topbar_end].strip() if topbar_start != -1 else ""

# Find scripts section
scripts_idx = content.rfind('<script src=')
body_end = content.rfind('</body>')
scripts_html = content[scripts_idx:body_end].strip() if scripts_idx != -1 else ""

print(f"Sidebar found: {sidebar_start != -1}")
print(f"Topbar found: {topbar_start != -1}")
print(f"Scripts found: {scripts_idx != -1}")

print("\n=== DONE ===")
print("Next step: Build Jinja2 base template using extracted HTML blocks")
