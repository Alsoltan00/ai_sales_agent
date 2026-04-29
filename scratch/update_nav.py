import os
import glob

nav_html = """        <div class="nav-links">
            <a href="/admin/dashboard" class="nav-item {% if 'dashboard' in request.url.path %}active{% endif %}"><i class="fa-solid fa-chart-pie"></i> نظرة عامة</a>
            
            {% set perms = user.permissions if user.permissions is mapping else {} %}
            {% set is_admin = perms.get('is_admin') %}
            
            {% if is_admin or perms.get('can_manage_new_clients') %}
            <a href="/admin/requests" class="nav-item {% if 'requests' in request.url.path %}active{% endif %}"><i class="fa-solid fa-user-plus"></i> العملاء الجدد</a>
            {% endif %}
            
            {% if is_admin or perms.get('can_manage_clients') %}
            <a href="/admin/clients" class="nav-item {% if 'clients' in request.url.path %}active{% endif %}"><i class="fa-solid fa-users"></i> إدارة العملاء</a>
            {% endif %}
            
            {% if is_admin or perms.get('can_manage_subscriptions') %}
            <a href="/admin/subscriptions" class="nav-item {% if 'subscriptions' in request.url.path %}active{% endif %}"><i class="fa-solid fa-id-card"></i> إدارة الاشتراكات</a>
            {% endif %}
            
            {% if is_admin or perms.get('can_manage_models') %}
            <a href="/admin/models-pool" class="nav-item {% if 'models-pool' in request.url.path %}active{% endif %}"><i class="fa-solid fa-cubes"></i> مكتبة النماذج</a>
            {% endif %}
            
            {% if is_admin or perms.get('can_manage_users') %}
            <a href="/admin/users" class="nav-item {% if 'users' in request.url.path %}active{% endif %}"><i class="fa-solid fa-users-gear"></i> إدارة المستخدمين</a>
            {% endif %}
        </div>"""

def replace_nav(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Find <div class="nav-links"> and its closing </div>
    start_idx = content.find('<div class="nav-links">')
    if start_idx == -1:
        return False
        
    # Find the next <div class="user-info"> which usually follows
    end_idx = content.find('<div class="user-info">', start_idx)
    if end_idx == -1:
        # Try finding the closing </div> of nav-links manually
        return False

    new_content = content[:start_idx] + nav_html + "\n        " + content[end_idx:]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"Updated {file_path}")
    return True

# Process templates
templates = glob.glob(r"c:\Users\Aseel\Desktop\ai_sales_agent\templates\admin*.html")
templates += glob.glob(r"c:\Users\Aseel\Desktop\ai_sales_agent\templates\admin\*.html")

for tmpl in templates:
    replace_nav(tmpl)
