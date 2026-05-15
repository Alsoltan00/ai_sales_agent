from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File
import shutil
import os
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import pandas as pd
import io
import json
import asyncio
from datetime import datetime
from pydantic import BaseModel
from auth.session_manager import get_current_user
from database.db_client import get_db_client

from merchant.store_management.store_settings import get_store_settings, update_store_settings
from merchant.planning.planning_config import get_planning_config, update_planning_config
from merchant.ai_training.ai_config import get_ai_config, update_ai_config
from merchant.data_sync.sync_config import get_sync_config, update_sync_config
from merchant.data_sync.google_sheets_sync import sync_sheet
from merchant.channels_config import get_channels_config, update_channels_config
from merchant.authorized_numbers import get_authorized_numbers, add_authorized_number, delete_authorized_number, set_allow_all, get_allow_all_status

router = APIRouter(prefix="/merchant", tags=["Merchant Home"])
templates = Jinja2Templates(directory="templates")

async def verify_merchant(request: Request):
    user = get_current_user(request)
    if not user or user.get("user_type") != "merchant":
        print(f"[VERIFY] Access denied or session missing for {request.url.path}")
        raise HTTPException(status_code=403, detail="غير مصرح لك بالدخول إلى لوحة التاجر")
    
    # جلب الإعدادات (باستخدام التخزين المؤقت لضمان سرعة الاستجابة ومنع الحجب)
    try:
        import time
        start_t = time.time()
        print(f"[VERIFY] Start metadata fetch for merchant: {user['id']}")
        
        # إضافة مهلة زمنية قصيرة لجلب الإعدادات لضمان عدم تعليق الصفحة إذا كانت قاعدة البيانات بطيئة
        try:
            planning_task = get_planning_config(user["id"])
            settings_task = get_store_settings(user["id"])
            
            # انتظار لمدة أقصاها 4 ثوانٍ فقط لجلب البيانات
            planning_res, settings_res = await asyncio.wait_for(
                asyncio.gather(planning_task, settings_task),
                timeout=4.0
            )
            
            user["_planning"] = planning_res
            user["_settings"] = settings_res
            print(f"[VERIFY] Metadata fetched in {time.time() - start_t:.3f}s for {user['id']}")
        except asyncio.TimeoutError:
            print(f"[VERIFY TIMEOUT] Database was slow, using defaults for {user['id']}")
            user["_planning"] = {}
            user["_settings"] = {}
            
    except Exception as e:
        print(f"[VERIFY ERROR] Critical failure in verify_merchant for {user['id']}: {e}")
        user["_planning"] = {}
        user["_settings"] = {}
        
    return user

@router.get("/dashboard", response_class=HTMLResponse)
async def merchant_home(request: Request):
    """لوحة التاجر - بدون verify_merchant لتجنب تجميد thread pool"""
    user = request.session.get("user")
    if not user or user.get("user_type") != "merchant":
        return RedirectResponse(url="/login", status_code=302)
    
    user_name = user.get("name", "التاجر")
    
    # صفحة تشخيصية مؤقتة
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>لوحة التحكم</title></head>
<body style="background:#0f172a;color:white;font-family:Arial;text-align:center;padding:80px;">
<h1>&#10004; مرحباً {user_name}</h1>
<p>تم الدخول للوحة التحكم بنجاح!</p>
<p style="margin-top:20px;"><a href="/auth/logout" style="color:#f59e0b;">تسجيل الخروج</a></p>
</body></html>"""
    return HTMLResponse(content=html, status_code=200)

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة الإعداد الأولي (Onboarding Wizard)"""
    planning = user["_planning"]
    return templates.TemplateResponse("merchant/onboarding.html", {"request": request, "user": user, "planning": planning})

@router.post("/api/onboarding")
def api_save_onboarding(payload: dict, user: dict = Depends(verify_merchant)):
    """حفظ الإعداد الأولي (نوع المبيعات + مسار الطلب + طبيعة المنتج)"""
    sales_type = payload.get("sales_type")
    order_flow = payload.get("order_flow")
    delivery_type = payload.get("delivery_type", "physical")
    
    if not sales_type or not order_flow:
        return {"status": "error", "message": "يرجى اختيار كل الخيارات المتاحة"}
    
    try:
        # حفظ في planning_config
        update_planning_config(user["id"], {
            "sales_type": sales_type,
            "order_flow": order_flow,
            "delivery_type": delivery_type
        })
        # تحديث حالة الإعداد الأولي
        update_store_settings(user["id"], {"onboarding_completed": True})
        return {"status": "success", "message": "تم حفظ الإعداد بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}


# --- Store Management ---

class StoreSettingsRequest(BaseModel):
    company_name: str
    contact_number: str
    email: str = None
    store_url: str = None

@router.get("/store", response_class=HTMLResponse)
async def store_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة إدارة المتجر (alias لـ /settings)"""
    settings = user["_settings"]
    return templates.TemplateResponse("merchant/store_settings.html", {"request": request, "user": user, "settings": settings})

@router.get("/settings", response_class=HTMLResponse)
async def store_settings_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة إعدادات المتجر"""
    settings = user["_settings"]
    return templates.TemplateResponse("merchant/store_settings.html", {"request": request, "user": user, "settings": settings})

@router.post("/api/store")
def api_update_store(request: Request, payload: StoreSettingsRequest, user: dict = Depends(verify_merchant)):
    """تحديث بيانات المتجر"""
    success = update_store_settings(user["id"], payload.model_dump())
    if success:
        # تحديث الاسم في الجلسة ليظهر التغيير فوراً في الواجهات
        if "user" in request.session:
            request.session["user"]["name"] = payload.company_name
        return {"status": "success", "message": "تم تحديث الإعدادات بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء التحديث"}

@router.post("/api/store/logo")
def api_upload_logo(file: UploadFile = File(...), user: dict = Depends(verify_merchant)):
    """رفع شعار المتجر وحفظه محلياً"""
    try:
        # إنشاء المجلد إذا لم يكن موجوداً
        logo_dir = "static/logos"
        if not os.path.exists(logo_dir):
            os.makedirs(logo_dir)
            
        # تحديد المسار واسم الملف
        ext = file.filename.split(".")[-1] if "." in file.filename else "png"
        filename = f"logo_{user['id']}.{ext}"
        file_path = os.path.join(logo_dir, filename)
        
        # حفظ الملف
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        logo_url = f"/static/logos/{filename}"
        
        # تحديث قاعدة البيانات
        from merchant.store_management.store_settings import update_store_settings
        update_store_settings(user["id"], {"logo_url": logo_url})
        
        return {"status": "success", "message": "تم رفع الشعار بنجاح", "logo_url": logo_url}
    except Exception as e:
        print(f"Error uploading logo: {e}")
        return {"status": "error", "message": f"حدث خطأ أثناء الرفع: {str(e)}"}

class PasswordChangeRequest(BaseModel):
    new_password: str

@router.post("/api/store/password")
def api_change_password(payload: PasswordChangeRequest, user: dict = Depends(verify_merchant)):
    """تغيير كلمة مرور التاجر"""
    import hashlib
    if len(payload.new_password) < 6:
        return {"status": "error", "message": "كلمة المرور يجب أن تكون 6 أحرف على الأقل"}
    hashed = hashlib.sha256(payload.new_password.encode()).hexdigest()
    db = get_db_client()
    try:
        db.table("clients").update({"password_hash": hashed}).eq("id", user["id"]).execute()
        return {"status": "success", "message": "تم تحديث كلمة المرور بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}

# --- Planning ---

class PlanningRequest(BaseModel):
    ai_agent_name: str = None
    ai_tone: str = None
    business_description: str = None
    store_activity: str = None
    custom_instructions: str = None
    ai_temperature: float = None
    ai_max_tokens: int = None
    ai_core_strategy: str = None

@router.get("/planning", response_class=HTMLResponse)
async def planning_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة التخطيط"""
    planning = user["_planning"]
    return templates.TemplateResponse("merchant/planning.html", {"request": request, "user": user, "planning": planning})

@router.post("/api/planning")
def api_update_planning(payload: PlanningRequest, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات التخطيط"""
    success = update_planning_config(user["id"], payload.model_dump())
    if success:
        return {"status": "success", "message": "تم تحديث بيانات التخطيط بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء التحديث"}



@router.post("/api/planning/generate-core-strategy")
async def api_generate_core_strategy(user: dict = Depends(verify_merchant)):
    """
    توليد 'الجوهر الاستراتيجي' الذكي للموظف الآلي.
    يحلل 100% من بيانات المتجر، يستخرج الفئات والأنماط،
    ويبني دستوراً تشغيلياً يتكيف مع حجم المخزون (قليل/متوسط/كبير).
    """
    from merchant.ai_engine import get_ai_response
    from database.db_client import get_db_client
    
    db = get_db_client()
    
    try:
        # ═══════════════════════════════════════════════════════════════
        # 1. جلب كل البيانات الممكنة للتحليل الشامل
        # ═══════════════════════════════════════════════════════════════
        
        # أ - جلب كامل المنتجات/الخدمات (100%)
        data_res = db.table("merchant_manual_data").select("data").eq("client_id", user["id"]).execute()
        products_raw = data_res.data[0].get("data", []) if data_res.data else []
        total_items = len(products_raw)
        
        # ب - جلب ملاحظات تدريب الأعمدة (مع حالة الإيقاف وعند الطلب)
        col_res = db.table("column_training").select("column_name, note, is_disabled, on_request").eq("client_id", user["id"]).execute()
        col_notes = col_res.data or []
        
        # ج - جلب قواعد العمل
        rules_res = db.table("business_rules").select("rules_data").eq("client_id", user["id"]).execute()
        biz_rules = rules_res.data[0].get("rules_data", {}) if rules_res.data else {}
        
        # د - جلب إعدادات التخطيط العامة
        plan_res = db.table("planning_config").select("*").eq("client_id", user["id"]).single().execute()
        plan_data = plan_res.data or {}
        
        if total_items == 0:
            return {"status": "error", "message": "لا توجد بيانات مزامنة في المتجر حالياً. يرجى إضافة بيانات أولاً من صفحة (مزامنة البيانات)."}

        # ═══════════════════════════════════════════════════════════════
        # 2. التحليل الآلي المحلي — استخراج الفئات والأنماط (خوارزميات فائقة السرعة)
        # ═══════════════════════════════════════════════════════════════
        
        # استخراج أسماء الأعمدة المفعلة
        disabled_cols = {c["column_name"] for c in col_notes if c.get("is_disabled")}
        active_cols = []
        if products_raw:
            active_cols = [k for k in products_raw[0].keys() if k not in disabled_cols]
        
        # ── أخذ عينة للتحليل السريع (لتفادي البطء في قواعد البيانات الضخمة 250k+) ──
        sample_size = min(total_items, 3000)
        analysis_sample = products_raw[:sample_size]
        
        # ── تحديد عمود التصنيف المحتمل (الفئة/القسم) ──
        category_keywords = ["فئة", "قسم", "تصنيف", "نوع", "مجموعة", "ماركة", "براند", "category", "type", "group", "section", "department", "brand", "model"]
        category_column = None
        categories_found = {}
        
        for col_name in active_cols:
            col_lower = col_name.lower().strip()
            if any(kw in col_lower for kw in category_keywords):
                unique_vals = set()
                for row in analysis_sample:
                    val = str(row.get(col_name, "")).strip()
                    if val: unique_vals.add(val)
                
                # إذا كان عدد القيم الفريدة معقول (يدعم حتى 200 فئة للمتاجر الضخمة)
                if 1 < len(unique_vals) <= 200:
                    category_column = col_name
                    break
        
        # الاكتشاف بالتكرار إذا لم نجد الكلمات المفتاحية (يعتمد على العينة فقط للسرعة)
        if not category_column and total_items > 5:
            best_col = None
            best_ratio = 0
            for col_name in active_cols:
                unique_vals = set()
                total_non_empty = 0
                for row in analysis_sample:
                    val = str(row.get(col_name, "")).strip()
                    if val:
                        total_non_empty += 1
                        if len(val) < 80: # استبعاد النصوص الطويلة
                            unique_vals.add(val)
                
                if len(unique_vals) < 2:
                    continue
                
                ratio = total_non_empty / len(unique_vals)
                
                if 2 <= len(unique_vals) <= min(200, total_non_empty // 2) and ratio >= 1.5:
                    if ratio > best_ratio:
                        best_ratio = ratio
                        best_col = col_name
            
            if best_col:
                category_column = best_col
        
        # ── استخراج الفئات وعدد العناصر الحقيقي (سريع جداً باستخدام Counter) ──
        if category_column:
            from collections import Counter
            cat_counter = Counter(str(row.get(category_column, "")).strip() for row in products_raw)
            cat_counter.pop("", None)
            
            if len(cat_counter) > 40:
                # أخذ أهم 40 فئة فقط لتجنب إغراق الذكاء الاصطناعي وتجاوز حدود الـ Tokens
                categories_found = dict(cat_counter.most_common(40))
                other_count = sum(count for _, count in cat_counter.most_common()[40:])
                if other_count > 0:
                    categories_found["فئات أخرى..."] = other_count
            else:
                categories_found = dict(cat_counter)
        
        # 🆕 FALLBACK: إذا لم يتم العثور على فئات وعندي منتجات كثيرة، نطلب من الـ AI استنتاج الفئات من الأسماء
        if not categories_found and total_items > 10:
            # البحث عن عمود الاسم
            name_col = None
            for col_name in active_cols:
                if any(kw in col_name.lower() for kw in ["اسم", "name", "منتج", "service", "عنوان"]):
                    name_col = col_name
                    break
            if not name_col and active_cols: name_col = active_cols[0]
            
            if name_col:
                # تقليل العينة لـ 30 فقط لتسريع التوليد (يكفي لاكتشاف النمط العام)
                names_sample = [str(r.get(name_col, "")).strip() for r in analysis_sample if r.get(name_col)][:30]
                clustering_prompt = f"""أنا لدي متجر يحتوي على المنتجات التالية: {", ".join(names_sample)}.
أريدك أن تستخرج لي 5 إلى 8 "فئات كبرى" (Keywords Categories) منطقية تجمع هذه المنتجات.
لكل فئة، استخرج أيضاً 3-4 "كلمات بحث مفتاحية" (Search Keywords) مرتبطة بها تساعد في البحث في قاعدة البيانات (مثال: فئة "إزالة المكياج" كلماتها هي: ["مزيل", "مكياج", "منظف"]).
رد علي بتنسيق JSON حصراً ككائن (Object) مفتاحه اسم الفئة وقيمته قائمة الكلمات المفتاحية: {{"فئة1": ["كلمة1", "كلمة2"], ...}}"""
                
                try:
                    cluster_res = await get_ai_response(
                        client_id=user["id"],
                        user_message=clustering_prompt,
                        phone_number="CLUSTERING",
                        channel="system"
                    )
                    # تنظيف الرد وجلبه كـ dict
                    import re
                    json_match = re.search(r'\{.*\}', cluster_res.replace("\n", ""), re.DOTALL)
                    if json_match:
                        suggested_map = json.loads(json_match.group(0))
                        for cat, keywords in suggested_map.items():
                            categories_found[cat] = keywords # حفظ الكلمات المفتاحية بدلاً من نص ثابت
                except:
                    pass

        # ── تحديد مستوى حجم المخزون ──
        if total_items <= 6:
            inventory_level = "صغير"
            inventory_strategy = "عرض_مباشر"
        elif total_items <= 20:
            inventory_level = "متوسط"
            inventory_strategy = "فئات_بسيطة" if categories_found else "عرض_مباشر"
        else:
            inventory_level = "كبير"
            inventory_strategy = "فئات_إلزامية"
        
        # ── بناء خريطة ملخص البيانات ──
        sample_products = []
        if categories_found and category_column:
            items_per_cat = max(1, min(3, 15 // len(categories_found)))
            for cat_name in list(categories_found.keys())[:15]: # أخذ عينة من أهم 15 فئة كحد أقصى
                cat_items = [r for r in analysis_sample if str(r.get(category_column, "")).strip() == cat_name]
                sample_products.extend(cat_items[:items_per_cat])
            sample_products = sample_products[:15]
        else:
            sample_products = analysis_sample[:15]
            
        # تنظيف العينة وتقليص النصوص الطويلة جداً لتقليل استهلاك التوكنز وتسريع الذكاء الاصطناعي
        clean_sample = []
        for row in sample_products:
            c_row = {}
            for k in active_cols:
                v = str(row.get(k, "")).strip()
                if v:
                    # قص النصوص التي تتجاوز 100 حرف
                    c_row[k] = v if len(v) <= 100 else v[:97] + "..."
            if c_row:
                clean_sample.append(c_row)
        
        # ── بناء ملخص الأعمدة النشطة مع ملاحظاتها ──
        col_summary = []
        for c in col_notes:
            status = "🔴 موقوف" if c.get("is_disabled") else ("🟡 عند الطلب" if c.get("on_request") else "🟢 نشط")
            note = c.get("note", "").strip()
            col_summary.append(f"  - {c['column_name']}: [{status}]{f' — ملاحظة: {note}' if note else ''}")
        
        # ═══════════════════════════════════════════════════════════════
        # 3. بناء طلب التحليل العميق (Meta-Prompt) مع كل البيانات المحللة
        # ═══════════════════════════════════════════════════════════════
        
        categories_text = ""
        if categories_found:
            cat_lines = [f"    • {cat}: {count} عنصر" for cat, count in sorted(categories_found.items(), key=lambda x: x[1], reverse=True)]
            categories_text = f"""
## الفئات المُستخرجة من البيانات (عمود التصنيف: "{category_column}"):
{chr(10).join(cat_lines)}
"""
        else:
            categories_text = """
## لم يتم العثور على عمود تصنيف واضح.
- البيانات لا تحتوي على فئات/أقسام.
"""

        analysis_prompt = f"""أنت "كبير استراتيجيي المبيعات والذكاء الاصطناعي".
مهمتك هي بناء "الجوهر الاستراتيجي الثابت" (Operational DNA) لموظف مبيعات ذكي.

═══════════════════════════════════════
📊 تقرير التحليل الآلي (تم تحليله مسبقاً بواسطة النظام):
═══════════════════════════════════════

• إجمالي العناصر في قاعدة البيانات: {total_items} عنصر
• مستوى حجم المخزون: {inventory_level}
• استراتيجية العرض المُقترحة: {inventory_strategy}
• عمود التصنيف المُكتشف: {category_column or "لا يوجد"}
• عدد الفئات المكتشفة: {len(categories_found) if categories_found else 0}
{categories_text}

## إعدادات المتجر:
- النشاط: {plan_data.get('store_activity', 'غير محدد')}
- وصف العمل: {plan_data.get('company_description', 'غير محدد')}
- نوع المبيعات: {plan_data.get('sales_type', 'products')}
- طريقة التسليم: {plan_data.get('delivery_type', 'physical')}
- مسار الطلب: {plan_data.get('order_flow', 'in_chat')}

## خريطة الأعمدة وحالاتها:
{chr(10).join(col_summary) if col_summary else '  لا توجد ملاحظات أعمدة.'}

## قواعد العمل المحفوظة:
{json.dumps(biz_rules, ensure_ascii=False) if biz_rules else 'لا توجد قواعد عمل.'}

## عينة ممثلة من البيانات (مختصرة لفهم الهيكلية والمحتوى):
{json.dumps(clean_sample, ensure_ascii=False)}

═══════════════════════════════════════
📝 المطلوب:
═══════════════════════════════════════

بناءً على التحليل أعلاه، اكتب "الجوهر الاستراتيجي" بالشكل التالي بالضبط:

### 1. هوية العرض (كيف أعرض البيانات للعميل):
{"- **إذا كان المخزون صغيراً (6 عناصر أو أقل)**: اكتب قانوناً صريحاً يأمر الموظف بعرض جميع العناصر مباشرة كأزرار دون فئات ودون أسئلة استكشافية، لأن تصنيفها سيضيع وقت العميل." if total_items <= 6 else ""}
{"- **إذا كان المخزون متوسطاً أو كبيراً وتوجد فئات**: اكتب قانوناً يأمر الموظف بعرض الفئات أولاً كأزرار، ثم بعد اختيار الفئة يعرض العناصر." if categories_found and total_items > 6 else ""}
{"- **إذا كان المخزون كبيراً ولا توجد فئات واضحة**: اكتب قانوناً يأمر الموظف بطرح سؤال استكشافي واحد لفهم حاجة العميل قبل العرض." if not categories_found and total_items > 6 else ""}
- **اذكر أسماء الفئات الفعلية** المُستخرجة أعلاه (إن وجدت) ليستخدمها الموظف حرفياً.
- **اذكر عدد العناصر في كل فئة** ليعرف الموظف ماذا يتوقع.

### 2. بروتوكول الأعمدة (ما يُعرض وما يُخفى):
- لكل عمود نشط، اكتب تعليمة واحدة واضحة (هل يُعرض تلقائياً؟ هل يُذكر فقط عند الطلب؟).
- الأعمدة الموقوفة يجب أن تُذكر بقانون "يُمنع ذكرها نهائياً".

### 3. خريطة البيانات الحية (Data Map):
- اكتب ملخصاً مضغوطاً لما يحتويه المتجر فعلياً (الأنواع، نطاق الأسعار، أي أنماط ملحوظة).
- هذا يمنع الموظف من الهلوسة لأنه سيعرف بالضبط ما لديه.

### 4. قوانين الجوهر الصارمة:
- قوانين خاصة بهذا المتجر تحديداً بناءً على طبيعة بياناته.

⚠️ تعليمات الكتابة:
- اكتب بأسلوب "دستوري صارم" (أوامر مباشرة، لا اقتراحات).
- استخدم "يجب"، "يُمنع"، "إلزامي" بدلاً من "يُفضل" أو "يمكن".
- الاستراتيجية يجب أن تكون عملية 100% وقابلة للتطبيق الفوري.
- اكتب باللغة العربية."""

        # ═══════════════════════════════════════════════════════════════
        # 4. إرسال للذكاء الاصطناعي لتوليد الاستراتيجية
        # ═══════════════════════════════════════════════════════════════
        try:
            core_strategy = await get_ai_response(
                client_id=user["id"],
                user_message=analysis_prompt,
                phone_number="STRATEGY_GEN",
                channel="system"
            )
        except Exception as e:
            if "context_length_exceeded" in str(e):
                 return {"status": "error", "message": "بيانات المتجر كبيرة جداً للتحليل الحالي، يرجى تقليل ملاحظات الأعمدة أو الوصف."}
            raise e
        
        # ═══════════════════════════════════════════════════════════════
        # 5. إضافة الهيدر التحليلي الآلي (بيانات ثابتة لا تتغير)
        # ═══════════════════════════════════════════════════════════════
        
        # بناء خريطة الفئات للحقن المباشر في الدستور
        auto_header = f"""## ═══ بيانات التحليل الآلي (حقائق ثابتة — لا تتجاهلها أبداً) ═══
- إجمالي العناصر في المتجر: {total_items}
- حجم المخزون: {inventory_level}
- استراتيجية العرض المُلزمة: {"عرض جميع العناصر مباشرة كأزرار (بدون فئات)" if inventory_strategy == "عرض_مباشر" else f"عرض الفئات أولاً ثم العناصر" if categories_found else "سؤال استكشافي ثم عرض"}
"""
        if categories_found:
            auto_header += f"- عمود التصنيف: {category_column or 'تحليل ذكي (Smart Analysis)'}\n"
            auto_header += "- الفئات المتاحة (استخدمها حرفياً كأزرار، واستخدم كلمات البحث الملحقة بها للعثور على المنتجات في القاعدة):\n"
            for cat, val in sorted(categories_found.items(), key=lambda x: x[0]):
                if isinstance(val, list):
                    # عرض الفئة مع كلمات البحث الخاصة بها
                    auto_header += f"  • {cat} (كلمات البحث: {', '.join(val)})\n"
                else:
                    auto_header += f"  • {cat} ({val} عنصر)\n"
        
        if inventory_strategy == "عرض_مباشر" and total_items <= 6:
            # في حالة المنتجات القليلة: نضيف أسماء كل العناصر
            name_col = None
            for col_name in active_cols:
                col_lower = col_name.lower().strip()
                if any(kw in col_lower for kw in ["اسم", "name", "منتج", "خدمة", "عنوان", "title", "product"]):
                    name_col = col_name
                    break
            if not name_col and active_cols:
                name_col = active_cols[0]
            
            if name_col:
                auto_header += f"\n- **العناصر الكاملة (اعرضها جميعاً مباشرة):**\n"
                for i, row in enumerate(products_raw[:6], 1):
                    item_name = str(row.get(name_col, f"عنصر {i}")).strip()
                    auto_header += f"  {i}. {item_name}\n"
        
        auto_header += "\n## ═══ الاستراتيجية المولّدة ═══\n"
        
        final_strategy = auto_header + core_strategy
        
        # ═══════════════════════════════════════════════════════════════
        # 6. حفظ الاستراتيجية في قاعدة البيانات
        # ═══════════════════════════════════════════════════════════════
        try:
            db.table("planning_config").update({"ai_core_strategy": final_strategy}).eq("client_id", user["id"]).execute()
        except Exception as db_err:
            if "column" in str(db_err) and "does not exist" in str(db_err):
                 return {"status": "error", "message": "قاعدة البيانات لم يتم تحديثها بالعمود الجديد. يرجى إعادة تشغيل السيرفر أو التواصل مع الدعم."}
            raise db_err
        
        return {
            "status": "success", 
            "strategy": final_strategy,
            "analysis": {
                "total_items": total_items,
                "inventory_level": inventory_level,
                "strategy_type": inventory_strategy,
                "categories_count": len(categories_found),
                "category_column": category_column,
                "categories": categories_found
            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"فشل توليد الجوهر الاستراتيجي: {str(e)}"}

@router.get("/api/planning/columns")
def api_get_columns(user: dict = Depends(verify_merchant)):
    """جلب أعمدة البيانات المزامنة مع إعدادات التدريب"""
    db = get_db_client()
    try:
        # الحل لتفادي نفاذ الذاكرة (OOM) في قواعد البيانات الضخمة (250k+):
        # نعتمد بشكل أساسي على ما تم حفظه في إعدادات التدريب سابقاً
        saved_res = db.table("column_training").select("*").eq("client_id", user["id"]).execute()
        saved_map = {r["column_name"]: r for r in (saved_res.data or [])}
        
        col_names = []
        if saved_map:
            # إذا كان التاجر قد حفظ الأعمدة مسبقاً، نستخدمها مباشرة لتفادي جلب البيانات الضخمة
            col_names = list(saved_map.keys())
        else:
            # إذا لم تكن محفوظة، سنضطر لجلب البيانات لكن سنستخدم PostgREST لجلب أول عنصر فقط لتفادي انهيار الخادم
            try:
                # محاولة جلب الصف بالكامل، ولكن نرجو ألا تنهار الذاكرة!
                # يفضل في تحديث قادم فصل هيكل الأعمدة في جدول منفصل أثناء المزامنة
                data_res = db.table("merchant_manual_data").select("data").eq("client_id", user["id"]).single().execute()
                if data_res.data and data_res.data.get("data"):
                    rows = data_res.data["data"]
                    if isinstance(rows, str):
                        import json
                        rows = json.loads(rows)
                    if rows and len(rows) > 0:
                        col_names = list(rows[0].keys())
            except Exception as inner_e:
                print(f"Error fetching columns from massive data: {inner_e}")
                pass

        columns = [{
            "name": c,
            "note": saved_map.get(c, {}).get("note", ""),
            "is_disabled": saved_map.get(c, {}).get("is_disabled", False),
            "on_request": saved_map.get(c, {}).get("on_request", False)
        } for c in col_names]
        return {"columns": columns}
    except Exception as e:
        return {"columns": []}

class ColumnTrainingItem(BaseModel):
    column_name: str
    note: str = ""
    is_disabled: bool = False
    on_request: bool = False

class ColumnTrainingRequest(BaseModel):
    columns: list[ColumnTrainingItem]

@router.post("/api/planning/columns")
async def api_save_columns(payload: ColumnTrainingRequest, user: dict = Depends(verify_merchant)):
    """حفظ إعدادات الأعمدة - حذف كامل + إعادة إدراج دفعية"""
    def _save():
        db = get_db_client()
        db.table("column_training").delete().eq("client_id", user["id"]).execute()
        for col in payload.columns:
            db.table("column_training").insert({
                "client_id": user["id"],
                "column_name": col.column_name,
                "note": col.note,
                "is_disabled": col.is_disabled,
                "on_request": col.on_request
            }).execute()
    try:
        await asyncio.to_thread(_save)
        return {"status": "success", "message": "تم حفظ إعدادات الأعمدة بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}



# --- Business Rules ---

@router.get("/business-rules", response_class=HTMLResponse)
async def business_rules_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة قواعد العمل (Business Rules)"""
    def _fetch_rules():
        db = get_db_client()
        try:
            res = db.table("business_rules").select("rules_data").eq("client_id", user["id"]).single().execute()
            if res.data:
                return res.data.get("rules_data", {})
        except:
            pass
        return {}
    rules = await asyncio.to_thread(_fetch_rules)
    return templates.TemplateResponse("merchant/business_rules.html", {"request": request, "user": user, "rules": rules})

@router.post("/api/business-rules")
def api_update_business_rules(payload: dict, user: dict = Depends(verify_merchant)):
    """تحديث قواعد العمل"""
    db = get_db_client()
    try:
        existing = db.table("business_rules").select("id").eq("client_id", user["id"]).execute()
        if existing.data:
            db.table("business_rules").update({
                "rules_data": payload,
                "updated_at": datetime.now().isoformat()
            }).eq("client_id", user["id"]).execute()
        else:
            db.table("business_rules").insert({
                "client_id": user["id"],
                "rules_data": payload,
                "updated_at": datetime.now().isoformat()
            }).execute()
        return {"status": "success", "message": "تم تحديث قواعد العمل بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}

@router.post("/api/business-rules/payment")
def api_update_payment_settings(payload: dict, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات الدفع والضريبة فقط (دمج مع القواعد الموجودة)"""
    db = get_db_client()
    try:
        res = db.table("business_rules").select("rules_data").eq("client_id", user["id"]).single().execute()
        current_rules = res.data.get("rules_data", {}) if res.data else {}
        for k, v in payload.items():
            current_rules[k] = v
        existing = db.table("business_rules").select("id").eq("client_id", user["id"]).execute()
        if existing.data:
            db.table("business_rules").update({
                "rules_data": current_rules,
                "updated_at": datetime.now().isoformat()
            }).eq("client_id", user["id"]).execute()
        else:
            db.table("business_rules").insert({
                "client_id": user["id"],
                "rules_data": current_rules,
                "updated_at": datetime.now().isoformat()
            }).execute()
        return {"status": "success", "message": "تم تحديث إعدادات الدفع والضريبة بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}



# --- Data Sync ---

class SyncConfigRequest(BaseModel):
    source_type: str
    connection_details: dict
    table_name: str = ""
    sheet_name: str = ""

@router.get("/data-sync", response_class=HTMLResponse)
async def data_sync_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة مزامنة البيانات"""
    sync_config = await asyncio.to_thread(get_sync_config, user["id"])
    return templates.TemplateResponse("merchant/data_sync.html", {"request": request, "user": user, "sync_config": sync_config})

@router.post("/api/data-sync")
async def api_update_data_sync(payload: SyncConfigRequest, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات المزامنة وتجربة المزامنة إذا كان جوجل شيت"""
    success = await asyncio.to_thread(update_sync_config, user["id"], payload.model_dump())
    if success:
        # إذا كان المختار هو جوجل شيت، نحاول المزامنة فوراً للتأكد من نجاح الربط
        if payload.source_type == "google_sheets":
            details = payload.connection_details
            if details and details.get("url"):
                sync_res = await sync_sheet(user["id"], details.get("url"), payload.sheet_name)
                if sync_res.get("status") == "success":
                    return {"status": "success", "message": f"تم الحفظ والمزامنة بنجاح: {sync_res.get('message')}"}
                else:
                    return {"status": "warning", "message": f"تم حفظ الإعدادات لكن المزامنة فشلت: {sync_res.get('message')}. تأكد أن الرابط عام (Anyone with link can view)."}
                    
        return {"status": "success", "message": "تم تحديث إعدادات الربط بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الربط"}

@router.post("/api/data-sync/upload")
async def api_upload_data_sync(file: UploadFile = File(...), user: dict = Depends(verify_merchant)):
    """رفع ومعالجة ملف Excel أو CSV يدوياً"""
    try:
        content = await file.read()
        filename = file.filename
        
        # قراءة الملف باستخدام pandas (الصف الأول هو العنوان تلقائياً)
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(content))
        else:
            df = pd.read_excel(io.BytesIO(content))
            
        # تنظيف البيانات: حذف الصفوف والأعمدة الفارغة تماماً
        df = df.dropna(how='all', axis=0).dropna(how='all', axis=1)
        
        # تحويل البيانات إلى JSON
        data_json = df.to_json(orient="records", force_ascii=False)
        
        db = get_db_client()
        
        # 1. تحديث إعدادات المزامنة لتكون excel
        update_sync_config(user["id"], {
            "source_type": "excel",
            "connection_details": {"filename": filename}
        })
        
        # 2. حفظ البيانات في الجدول الجديد
        try:
            db.table("merchant_manual_data").delete().eq("client_id", user["id"]).execute()
        except:
            pass
            
        db.table("merchant_manual_data").insert({
            "client_id": user["id"],
            "data": json.loads(data_json),
            "filename": filename,
            "updated_at": datetime.now().isoformat()
        }).execute()
        
        return {"status": "success", "message": f"تم رفع ومعالجة الملف '{filename}' بنجاح. تم استيراد {len(df)} سجل."}
        
    except Exception as e:
        print(f"Upload error: {str(e)}")
        return {"status": "error", "message": f"خطأ أثناء معالجة الملف: {str(e)}"}

# --- Channels Configuration (Reception & Sending) ---

class ChannelsConfigRequest(BaseModel):
    telegram_bot_token: str = None
    whatsapp_provider: str = "evolution"
    evolution_api_url: str = None
    evolution_api_key: str = None
    evolution_instance_name: str = None
    meta_phone_number_id: str = None
    meta_access_token: str = None
    meta_verify_token: str = None
    instagram_access_token: str = None
    instagram_page_id: str = None
    tiktok_access_token: str = None
    tiktok_shop_id: str = None

@router.get("/channels", response_class=HTMLResponse)
async def channels_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة الاستقبال والإرسال"""
    from merchant.authorized_numbers import get_authorized_numbers, get_allow_all_status, get_ignore_groups_status
    # تنفيذ جميع الاستعلامات بالتوازي بدلاً من التتابع (4x أسرع)
    channels_config, numbers, allow_all, ignore_groups = await asyncio.gather(
        asyncio.to_thread(get_channels_config, user["id"]),
        asyncio.to_thread(get_authorized_numbers, user["id"]),
        asyncio.to_thread(get_allow_all_status, user["id"]),
        asyncio.to_thread(get_ignore_groups_status, user["id"]),
    )
    
    return templates.TemplateResponse("merchant/channels.html", {
        "request": request, 
        "user": user, 
        "channels_config": channels_config,
        "numbers": numbers,
        "allow_all": allow_all,
        "ignore_groups": ignore_groups
    })

@router.post("/api/channels")
async def api_update_channels(request: Request, payload: ChannelsConfigRequest, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات القنوات والتسجيل التلقائي للويب هوك"""
    success = await asyncio.to_thread(update_channels_config, user["id"], payload.model_dump())
    if success:
        if payload.telegram_bot_token:
            try:
                import httpx
                host = request.headers.get("host", request.url.hostname)
                scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
                if host and ":" not in host and host != "localhost":
                    scheme = "https"
                webhook_url = f"{scheme}://{host}/webhook/telegram/{payload.telegram_bot_token}"
                
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"https://api.telegram.org/bot{payload.telegram_bot_token}/setWebhook",
                        json={"url": webhook_url}
                    )
            except Exception as e:
                print(f"Error setting Telegram webhook: {e}")
                
        return {"status": "success", "message": "تم حفظ إعدادات القنوات بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الحفظ"}

@router.post("/api/channels/test-whatsapp")
async def api_test_whatsapp(user: dict = Depends(verify_merchant)):
    """اختبار إرسال رسالة واتساب تجريبية"""
    from merchant.reception.whatsapp_evolution_receiver import _send_evolution_message
    from merchant.channels_config import get_channels_config
    from merchant.authorized_numbers import get_authorized_numbers

    # 1. جلب الإعدادات
    cfg = get_channels_config(user["id"])
    if not cfg or not cfg.get("evolution_api_url"):
        return {"status": "error", "message": "يرجى حفظ إعدادات Evolution API أولاً"}

    # 2. جلب أول رقم مصرح للإرسال له
    numbers = get_authorized_numbers(user["id"])
    if not numbers:
        return {"status": "error", "message": "يرجى إضافة رقم واحد على الأقل في قائمة الأرقام المصرّحة ليتم إرسال التجربة له"}
    
    test_phone = numbers[0]["phone_number"]
    test_msg = "🚀 تجربة ناجحة! السيرفر الخاص بك متصل الآن بـ Evolution API بشكل صحيح."

    # 3. محاولة الإرسال
    success = await _send_evolution_message(
        cfg["evolution_api_url"],
        cfg["evolution_api_key"],
        cfg["evolution_instance_name"],
        test_phone,
        test_msg
    )

    if success:
        return {"status": "success", "message": f"تم إرسال رسالة تجريبية بنجاح للرقم {test_phone}"}
    else:
        return {"status": "error", "message": "فشل الإرسال. تأكد من صحة الرابط، الـ API Key، واسم الجلسة."}

# --- WhatsApp QR Code Connection ---

@router.post("/api/whatsapp/connect")
async def api_whatsapp_connect(request: Request, user: dict = Depends(verify_merchant)):
    """إنشاء جلسة واتساب جديدة وجلب QR Code"""
    from merchant.evolution_service import create_instance
    host = request.headers.get("host", request.url.hostname)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    if host and ":" not in host and host != "localhost":
        scheme = "https"
    webhook_base = f"{scheme}://{host}"

    result = await create_instance(user["id"], webhook_base)
    return result

@router.get("/api/whatsapp/qr")
async def api_whatsapp_qr(user: dict = Depends(verify_merchant)):
    """جلب QR Code جديد للجلسة الحالية"""
    from merchant.evolution_service import get_qr_code
    result = await get_qr_code(user["id"])
    return result

@router.get("/api/whatsapp/status")
async def api_whatsapp_status(user: dict = Depends(verify_merchant)):
    """التحقق من حالة اتصال واتساب"""
    from merchant.evolution_service import check_connection_status
    result = await check_connection_status(user["id"])
    return result

@router.post("/api/whatsapp/disconnect")
async def api_whatsapp_disconnect(user: dict = Depends(verify_merchant)):
    """قطع اتصال واتساب"""
    from merchant.evolution_service import disconnect_instance
    result = await disconnect_instance(user["id"])
    return result

@router.post("/api/whatsapp/setup-webhook")
async def api_whatsapp_setup_webhook(request: Request, user: dict = Depends(verify_merchant)):
    """تسجيل Webhook تلقائياً بعد الاتصال"""
    from merchant.evolution_service import set_webhook
    host = request.headers.get("host", request.url.hostname)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    if host and ":" not in host and host != "localhost":
        scheme = "https"
    webhook_base = f"{scheme}://{host}"

    result = await set_webhook(user["id"], webhook_base)
    return result

# --- Authorized Numbers ---


class AuthorizedNumberRequest(BaseModel):
    phone_number: str
    label: str = ""

class AllowAllRequest(BaseModel):
    allow_all: bool

@router.post("/api/authorized-numbers")
def api_add_authorized_number(payload: AuthorizedNumberRequest, user: dict = Depends(verify_merchant)):
    """إضافة رقم جديد"""
    success = add_authorized_number(user["id"], payload.phone_number, payload.label)
    if success:
        return {"status": "success", "message": "تم إضافة الرقم بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الإضافة"}

@router.delete("/api/authorized-numbers/{record_id}")
def api_delete_authorized_number(record_id: str, user: dict = Depends(verify_merchant)):
    """حذف رقم"""
    success = delete_authorized_number(user["id"], record_id)
    if success:
        return {"status": "success", "message": "تم حذف الرقم بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الحذف"}

@router.post("/api/authorized-numbers/settings")
def api_update_authorized_settings(payload: dict, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات الأرقام والمجموعات"""
    from merchant.authorized_numbers import set_allow_all, set_ignore_groups
    
    if "allow_all" in payload:
        set_allow_all(user["id"], payload["allow_all"])
    
    if "ignore_groups" in payload:
        set_ignore_groups(user["id"], payload["ignore_groups"])
        
    return {"status": "success", "message": "تم تحديث الإعدادات بنجاح"}

class ClearMemoryRequest(BaseModel):
    phone_number: str

@router.post("/api/clear-memory")
def api_clear_customer_memory(payload: ClearMemoryRequest, user: dict = Depends(verify_merchant)):
    """مسح سجل المحادثات لعميل محدد (تصفير الذاكرة)"""
    db = get_db_client()
    try:
        raw_phone = payload.phone_number.strip()
        # التنظيف: إزالة + و 00 و أي لواحق واتساب أو أجهزة مرتبطة (:1)
        clean_phone = raw_phone.replace("+", "").split("@")[0].split(":")[0]
        if clean_phone.startswith("00"):
            clean_phone = clean_phone[2:]
        
        # مصفوفة احتمالات الرقم (بالسوابق المختلفة)
        variations = [
            raw_phone,
            clean_phone,
            f"{clean_phone}@s.whatsapp.net",
            f"+{clean_phone}",
            f"00{clean_phone}"
        ]
        
        # بناء شرط OR شامل
        or_filter = ",".join([f"phone_number.eq.{v}" for v in set(variations)])
        
        # تنفيذ الحذف
        res = db.table("message_logs").delete().eq("client_id", user["id"]).or_(or_filter).execute()
        
        deleted_count = len(res.data) if res.data else 0
        
        if deleted_count > 0:
            return {"status": "success", "message": f"تم مسح {deleted_count} رسالة من ذاكرة العميل بنجاح!"}
        else:
            return {"status": "success", "message": "لم يتم العثور على رسائل قديمة لهذا الرقم، الذاكرة فارغة بالفعل."}
            
    except Exception as e:
        print(f"Error clearing memory: {e}")
        return {"status": "error", "message": "حدث خطأ أثناء محاولة مسح الذاكرة"}

# --- Data Display View ---

@router.get("/data-view", response_class=HTMLResponse)
async def data_view_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة عرض البيانات المزامنة"""
    return templates.TemplateResponse("merchant/data_display.html", {"request": request, "user": user})

@router.get("/api/data-view")
def api_get_data_view(user: dict = Depends(verify_merchant)):
    """جلب البيانات المزامنة للعرض"""
    db = get_db_client()
    try:
        # جلب البيانات اليدوية (Excel/CSV)
        data_res = db.table("merchant_manual_data").select("data, filename").eq("client_id", user["id"]).single().execute()
        if data_res.data and data_res.data.get("data"):
            rows = data_res.data["data"]
            if isinstance(rows, str):
                try:
                    rows = json.loads(rows)
                except:
                    rows = []
            return {"status": "ok", "data": rows, "source_type": "excel"}

        # جلب إعدادات المزامنة لمعرفة المصدر
        sync_res = db.table("sync_config").select("source_type").eq("client_id", user["id"]).single().execute()
        source = sync_res.data.get("source_type", "") if sync_res.data else ""
        return {"status": "no_data", "data": [], "source_type": source}
    except Exception as e:
        return {"status": "no_data", "data": [], "source_type": ""}

# --- Orders Management ---

@router.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة إدارة الطلبات"""
    settings = user["_settings"]
    def _fetch_orders():
        db = get_db_client()
        try:
            res = db.table("orders").select("*").eq("client_id", user["id"]).order("created_at", desc=True).execute()
            return res.data or []
        except:
            return []
    def _fetch_rules():
        db = get_db_client()
        try:
            res = db.table("business_rules").select("rules_data").eq("client_id", user["id"]).single().execute()
            return res.data.get("rules_data", {}) if res.data else {}
        except:
            return {}
    # تنفيذ الاستعلامين بالتوازي
    orders, rules = await asyncio.gather(
        asyncio.to_thread(_fetch_orders),
        asyncio.to_thread(_fetch_rules),
    )

    # Safe stats calculation
    total_revenue = 0
    pending_count = 0
    confirmed_count = 0
    completed_count = 0
    
    for o in orders:
        # Ensure items is a list to prevent Jinja2 slicing errors
        items_data = o.get("items")
        if not isinstance(items_data, list):
            if isinstance(items_data, dict):
                o["items"] = [items_data]
            else:
                o["items"] = []
                
        # Ensure every item in the list is a dict to prevent item.get() crashing
        clean_items = []
        for it in o["items"]:
            if isinstance(it, dict):
                clean_items.append(it)
            elif isinstance(it, str):
                clean_items.append({"name": it, "qty": 1, "price": 0})
        o["items"] = clean_items
                
        # Revenue
        try:
            val = o.get("total_amount")
            if val is not None:
                o["total_amount"] = float(val)
                total_revenue += float(val)
            else:
                o["total_amount"] = 0.0
        except:
            o["total_amount"] = 0.0
            
        # Status counts
        status = o.get("order_status")
        if status == "pending":
            pending_count += 1
        elif status == "confirmed":
            confirmed_count += 1
        elif status in ["completed", "delivered"]:
            completed_count += 1

    import json as _json
    planning = user["_planning"]
    return templates.TemplateResponse("merchant/orders.html", {
        "request": request, "user": user,
        "orders": orders,
        "total_revenue": total_revenue,
        "pending_count": pending_count,
        "confirmed_count": confirmed_count,
        "completed_count": completed_count,
        "settings": settings,
        "rules": rules,
        "planning": planning,
        "orders_json": _json.dumps(orders, ensure_ascii=False, default=str)
    })

@router.post("/api/orders")
def api_create_order(payload: dict, user: dict = Depends(verify_merchant)):
    """إنشاء طلب يدوي جديد"""
    db = get_db_client()
    try:
        # توليد رقم طلب فريد
        import random
        order_num = f"ORD-{datetime.now().strftime('%y%m%d')}-{random.randint(1000,9999)}"
        
        order_data = {
            "client_id": user["id"],
            "order_number": order_num,
            "order_type": payload.get("order_type", "purchase"),
            "order_status": "pending",
            "customer_name": payload.get("customer_name", ""),
            "customer_phone": payload.get("customer_phone", ""),
            "customer_address": payload.get("customer_address", ""),
            "customer_city": payload.get("customer_city", ""),
            "items": payload.get("items", []),
            "total_amount": float(payload.get("total_amount", 0)),
            "payment_method": payload.get("payment_method"),
            "payment_status": "pending",
            "delivery_method": payload.get("delivery_method"),
            "channel": payload.get("channel", "manual"),
            "internal_notes": payload.get("internal_notes", ""),
            "currency": payload.get("currency", "SAR")
        }
        db.table("orders").insert(order_data).execute()
        return {"status": "success", "message": "تم إنشاء الطلب بنجاح", "order_number": order_num}
    except Exception as e:
        print(f"Error creating order: {e}")
        return {"status": "error", "message": str(e)}

@router.put("/api/orders/{order_id}/status")
def api_update_order_status(order_id: str, payload: dict, user: dict = Depends(verify_merchant)):
    """تحديث حالة الطلب والدفع"""
    db = get_db_client()
    try:
        update = {}
        if "order_status" in payload:
            update["order_status"] = payload["order_status"]
            if payload["order_status"] in ("completed", "delivered"):
                update["completed_at"] = datetime.utcnow().isoformat()
            if payload["order_status"] == "confirmed":
                update["confirmed_at"] = datetime.utcnow().isoformat()
        if "payment_status" in payload:
            update["payment_status"] = payload["payment_status"]
        
        db.table("orders").update(update).eq("id", order_id).eq("client_id", user["id"]).execute()
        return {"status": "success", "message": "تم تحديث الحالة"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.delete("/api/orders/{order_id}")
def api_delete_order(order_id: str, user: dict = Depends(verify_merchant)):
    """حذف طلب"""
    db = get_db_client()
    try:
        db.table("orders").delete().eq("id", order_id).eq("client_id", user["id"]).execute()
        return {"status": "success", "message": "تم حذف الطلب"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Shipping Management ---

@router.get("/shipping", response_class=HTMLResponse)
async def shipping_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة إعدادات الشحن"""
    def _fetch_config():
        db = get_db_client()
        try:
            res = db.table("shipping_config").select("*").eq("client_id", user["id"]).single().execute()
            return res.data if res.data else {}
        except:
            return {}
    def _fetch_zones():
        db = get_db_client()
        try:
            res = db.table("shipping_zones").select("*").eq("client_id", user["id"]).order("created_at").execute()
            return res.data or []
        except:
            return []
    # تنفيذ الاستعلامين بالتوازي
    config, zones = await asyncio.gather(
        asyncio.to_thread(_fetch_config),
        asyncio.to_thread(_fetch_zones),
    )
    return templates.TemplateResponse("merchant/shipping.html", {
        "request": request, "user": user, "config": config, "zones": zones
    })

@router.post("/api/planning")
async def api_save_planning(payload: dict, user: dict = Depends(verify_merchant)):
    """حفظ إعدادات الشحن ومناطق الشحن"""
    def _save_shipping():
        db = get_db_client()
        # 1. upsert الإعدادات العامة (استعلام واحد بدلاً من check+update/insert)
        config_data = {
            "client_id": user["id"],
            "unavailable_area_msg": payload.get("unavailable_area_msg", ""),
            "updated_at": datetime.now().isoformat()
        }
        db.table("shipping_config").upsert(config_data).execute()
        # 2. حذف المناطق القديمة وإضافة الجديدة
        db.table("shipping_zones").delete().eq("client_id", user["id"]).execute()
        zones = payload.get("zones", [])
        for z in zones:
            zone_name = z.get("zone_name", "").strip()
            if zone_name:
                db.table("shipping_zones").insert({
                    "client_id": user["id"],
                    "zone_name": zone_name,
                    "shipping_price": float(z.get("shipping_price", 0)),
                    "free_shipping_enabled": bool(z.get("free_shipping_enabled", False)),
                    "free_shipping_min": float(z.get("free_shipping_min", 0))
                }).execute()
    try:
        await asyncio.to_thread(_save_shipping)
        return {"status": "success", "message": "تم حفظ إعدادات الشحن بنجاح"}
    except Exception as e:
        print(f"Error saving shipping config: {e}")
        return {"status": "error", "message": str(e)}

# --- AI Insights ---

@router.get("/insights", response_class=HTMLResponse)
async def insights_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة رؤى العملاء المتقدمة"""
    return templates.TemplateResponse("merchant/insights.html", {"request": request, "user": user})

@router.get("/api/insights")
def api_get_insights(user: dict = Depends(verify_merchant)):
    """جلب آخر رؤى تم توليدها"""
    from merchant.insights import get_latest_insights
    try:
        data = get_latest_insights(user["id"])
        return {"status": "success", "data": data}
    except Exception as e:
        if "merchant_ai_insights" in str(e) and "does not exist" in str(e):
            return {"status": "success", "data": {}}
        return {"status": "error", "message": str(e)}

@router.post("/api/insights/generate")
async def api_generate_insights(user: dict = Depends(verify_merchant)):
    """طلب توليد رؤى جديدة من المحادثات"""
    from merchant.insights import generate_and_save_insights
    from database.db_client import get_db_engine
    from sqlalchemy import text
    
    # محاولة إنشاء الجدول بشكل استباقي قبل البدء
    engine = get_db_engine()
    if engine:
        try:
            with engine.begin() as conn:
                pc_cols = [r[0] for r in conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='planning_config'")).fetchall()]
                if 'ai_max_tokens' not in pc_cols:
                    conn.execute(text("ALTER TABLE planning_config ADD COLUMN ai_max_tokens INTEGER DEFAULT 600;"))
                if 'ai_core_strategy' not in pc_cols:
                    conn.execute(text("ALTER TABLE planning_config ADD COLUMN ai_core_strategy TEXT DEFAULT '';"))
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS merchant_ai_insights (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        client_id UUID REFERENCES clients(id) ON DELETE CASCADE,
                        insights_data JSONB DEFAULT '{}',
                        period TEXT DEFAULT 'last_7_days',
                        created_at TIMESTAMP DEFAULT NOW()
                    );
                """))
        except Exception as e:
            print(f"Pre-emptive table creation warning: {e}")

    try:
        res = await generate_and_save_insights(user["id"])
        return res
    except Exception as e:
        return {"status": "error", "message": str(e)}

# --- Customer Management (CRM) ---

@router.get("/customers", response_class=HTMLResponse)
async def customers_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة إدارة العملاء (تتكيف ديناميكياً مع نوع المتجر)"""
    from merchant.customers.customer_manager import get_all_customers
    customers = await asyncio.to_thread(get_all_customers, user["id"])
    planning = user["_planning"]
    return templates.TemplateResponse("merchant/customers.html", {
        "request": request, "user": user, "customers": customers, "planning": planning
    })

@router.get("/api/customers")
def api_get_customers(user: dict = Depends(verify_merchant)):
    """جلب جميع العملاء كـ JSON"""
    from merchant.customers.customer_manager import get_all_customers
    customers = get_all_customers(user["id"])
    return {"status": "success", "customers": customers}

@router.put("/api/customers/{customer_id}")
def api_update_customer(customer_id: str, payload: dict, user: dict = Depends(verify_merchant)):
    """تحديث بيانات عميل"""
    from merchant.customers.customer_manager import update_customer_data
    db = get_db_client()
    try:
        # جلب المعرف الرئيسي للعميل
        res = db.table("customer_profiles").select("platform_identifier").eq("id", customer_id).eq("client_id", user["id"]).single().execute()
        if not res.data:
            return {"status": "error", "message": "العميل غير موجود"}
        
        identifier = res.data["platform_identifier"]
        updates = {}
        if "customer_name" in payload:
            updates["customer_name"] = payload["customer_name"]
        if "customer_address" in payload:
            updates["customer_address"] = payload["customer_address"]
        if "customer_city" in payload:
            updates["customer_city"] = payload["customer_city"]
        if "phone_number" in payload:
            updates["phone_number"] = payload["phone_number"]
        
        if updates:
            update_customer_data(user["id"], identifier, updates)
            return {"status": "success", "message": "تم تحديث بيانات العميل بنجاح"}
        return {"status": "error", "message": "لا توجد بيانات للتحديث"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.delete("/api/customers/{customer_id}")
def api_delete_customer(customer_id: str, user: dict = Depends(verify_merchant)):
    """حذف عميل"""
    from merchant.customers.customer_manager import delete_customer
    success = delete_customer(user["id"], customer_id)
    if success:
        return {"status": "success", "message": "تم حذف العميل بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الحذف"}


# --- AI Playground (Simulation) ---

@router.get("/playground", response_class=HTMLResponse)
async def playground_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة مختبر الذكاء (التجربة الحية)"""
    return templates.TemplateResponse("merchant/playground.html", {"request": request, "user": user})

class PlaygroundChatRequest(BaseModel):
    message: str
    platform: str = "whatsapp" # whatsapp, telegram, instagram, tiktok
    reset_memory: bool = False

@router.post("/api/playground-chat")
async def api_playground_chat(payload: PlaygroundChatRequest, user: dict = Depends(verify_merchant)):
    """API لمحاكاة الدردشة مع الذكاء الاصطناعي عبر منصات مختلفة"""
    from merchant.ai_engine import get_ai_response
    from database.db_client import get_db_client
    
    # معرف وهمي للجلسة لمحاكاة منصة الاختبار
    test_phone = f"PLAYGROUND_{payload.platform.upper()}"
    
    db = get_db_client()
    
    # إذا طلب المستخدم تصفير الذاكرة قبل الإرسال
    if payload.reset_memory:
        try:
            db.table("message_logs").delete().eq("client_id", user["id"]).eq("phone_number", test_phone).execute()
        except:
            pass

    try:
        response = await get_ai_response(
            client_id=user["id"],
            user_message=payload.message,
            phone_number=test_phone,
            channel=payload.platform
        )
        return {"status": "success", "response": response}
    except Exception as e:
        return {"status": "error", "message": str(e)}
