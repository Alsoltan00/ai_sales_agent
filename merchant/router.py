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
            planning_task = asyncio.create_task(get_planning_config(user["id"]))
            settings_task = asyncio.create_task(get_store_settings(user["id"]))
            
            # استخدام asyncio.wait بدلاً من wait_for لضمان عدم التعليق إذا فشل إلغاء الثريد
            done, pending = await asyncio.wait(
                [planning_task, settings_task],
                timeout=4.0
            )
            
            if pending:
                print(f"[VERIFY TIMEOUT] Database was slow, using defaults for {user['id']}")
                user["_planning"] = {}
                user["_settings"] = {}
            else:
                user["_planning"] = planning_task.result()
                user["_settings"] = settings_task.result()
            print(f"[VERIFY] Metadata fetched in {time.time() - start_t:.3f}s for {user['id']}")
            
        except Exception as e:
            print(f"[VERIFY ERROR] {e}")
            user["_planning"] = {}
            user["_settings"] = {}
            
    except Exception as e:
        print(f"[VERIFY ERROR] Critical failure in verify_merchant for {user['id']}: {e}")
        user["_planning"] = {}
        user["_settings"] = {}
        
    return user


@router.get("/dashboard", response_class=HTMLResponse)
async def merchant_home(request: Request, user: dict = Depends(verify_merchant)):
    """لوحة التاجر الرئيسية (Dashboard)"""
    settings = user["_settings"]
    planning = user["_planning"]
    
    print(f"[DASHBOARD] Rendering for user: {user.get('name', 'unknown')}, settings: {bool(settings)}, onboarding: {settings.get('onboarding_completed')}")
    
    # التحقق من إكمال الإعدادات الأساسية
    onboarding_completed = settings.get("onboarding_completed", False) if settings else False
    if not onboarding_completed:
        return RedirectResponse(url="/merchant/onboarding", status_code=303)

    return templates.TemplateResponse(
        "merchant_home.html",
        {
            "request": request,
            "user": user,
            "settings": settings,
            "planning": planning,
            "active_tab": "dashboard"
        }
    )

@router.get("/onboarding", response_class=HTMLResponse)
async def onboarding_page(request: Request, user: dict = Depends(verify_merchant)):
    """صفحة الإعداد الأولي (Onboarding Wizard)"""
    planning = user["_planning"]
    return templates.TemplateResponse("merchant/onboarding.html", {"request": request, "user": user, "planning": planning})

@router.post("/api/onboarding")
async def api_save_onboarding(payload: dict, user: dict = Depends(verify_merchant)):
    """حفظ الإعداد الأولي (نوع المبيعات + مسار الطلب + طبيعة المنتج)"""
    sales_type = payload.get("sales_type")
    order_flow = payload.get("order_flow")
    delivery_type = payload.get("delivery_type", "physical")
    
    if not sales_type or not order_flow:
        return {"status": "error", "message": "يرجى اختيار كل الخيارات المتاحة"}
    
    try:
        # حفظ في planning_config
        await asyncio.to_thread(update_planning_config, user["id"], {
            "sales_type": sales_type,
            "order_flow": order_flow,
            "delivery_type": delivery_type
        })
        # تحديث حالة الإعداد الأولي
        await asyncio.to_thread(update_store_settings, user["id"], {"onboarding_completed": True})
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
async def api_update_store(request: Request, payload: StoreSettingsRequest, user: dict = Depends(verify_merchant)):
    """تحديث بيانات المتجر"""
    success = await asyncio.to_thread(update_store_settings, user["id"], payload.model_dump())
    if success:
        # تحديث الاسم في الجلسة ليظهر التغيير فوراً في الواجهات
        if "user" in request.session:
            request.session["user"]["name"] = payload.company_name
        return {"status": "success", "message": "تم تحديث الإعدادات بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء التحديث"}

@router.post("/api/store/logo")
async def api_upload_logo(file: UploadFile = File(...), user: dict = Depends(verify_merchant)):
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
async def api_change_password(payload: PasswordChangeRequest, user: dict = Depends(verify_merchant)):
    """تغيير كلمة مرور التاجر"""
    import hashlib
    if len(payload.new_password) < 6:
        return {"status": "error", "message": "كلمة المرور يجب أن تكون 6 أحرف على الأقل"}
    hashed = hashlib.sha256(payload.new_password.encode()).hexdigest()
    db = get_db_client()
    try:
        await db.table("clients").update({"password_hash": hashed}).eq("id", user["id"]).execute_async()
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
async def api_update_planning(payload: PlanningRequest, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات التخطيط"""
    success = await asyncio.to_thread(update_planning_config, user["id"], payload.model_dump())
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
        data_res = await db.table("merchant_manual_data").select("data").eq("client_id", user["id"]).execute_async()
        products_raw = data_res.data[0].get("data", []) if data_res.data else []
        total_items = len(products_raw)
        
        # ب - جلب ملاحظات تدريب الأعمدة (مع حالة الإيقاف وعند الطلب)
        col_res = await db.table("column_training").select("column_name, note, is_disabled, on_request").eq("client_id", user["id"]).execute_async()
        col_notes = col_res.data or []
        
        # ج - جلب قواعد العمل
        rules_res = await db.table("business_rules").select("rules_data").eq("client_id", user["id"]).execute_async()
        biz_rules = rules_res.data[0].get("rules_data", {}) if rules_res.data else {}
        
        # د - جلب إعدادات التخطيط العامة
        plan_res = await db.table("planning_config").select("*").eq("client_id", user["id"]).single().execute_async()
        plan_data = plan_res.data or {}
        
        if total_items == 0:
            return {"status": "error", "message": "لا توجد بيانات مزامنة في المتجر حالياً. يرجى إضافة بيانات أولاً من صفحة (مزامنة البيانات)."}

        # ═══════════════════════════════════════════════════════════════
        # 2. التحليل الآلي المحلي — محرك اكتشاف الفئات والماركات v2.0
        #    Smart Column Classification + Statistical Scoring
        # ═══════════════════════════════════════════════════════════════
        
        from collections import Counter
        import re as regex_module
        
        # استخراج أسماء الأعمدة المفعلة
        disabled_cols = {c["column_name"] for c in col_notes if c.get("is_disabled")}
        active_cols = []
        if products_raw:
            active_cols = [k for k in products_raw[0].keys() if k not in disabled_cols]
        
        # ── أخذ عينة موزعة بانتظام للتحليل (Distributed Sampling) ──
        # بدلاً من أخذ أول 5000 (مما يفشل إذا كانت البيانات مرتبة)، نأخذ عينة تغطي كامل القاعدة
        sample_size = 5000
        if total_items <= sample_size:
            analysis_sample = products_raw
        else:
            # حساب الخطوة القفزية لضمان توزيع العينة من البداية للنهاية
            step = total_items // sample_size
            analysis_sample = products_raw[::step][:sample_size]

        
        # ═══════════════════════════════════════════════════════════════
        # 2.1 — تصنيف كل عمود حسب نوع بياناته الفعلية
        # ═══════════════════════════════════════════════════════════════
        
        def classify_column(col_name, rows, max_check=500):
            """
            يحلل عينة من قيم العمود ويصنفه إلى:
            - 'numeric': أرقام بحتة (IDs, أسعار, كميات)
            - 'url': روابط
            - 'timestamp': طوابع زمنية
            - 'long_text': نصوص طويلة (أوصاف, ملاحظات)
            - 'boolean': قيم منطقية
            - 'categorical': قيم تصنيفية (فئات، ماركات، أقسام)
            - 'identifier': معرفات فريدة (UUID, SKU)
            - 'empty': عمود فارغ غالباً
            """
            values = []
            empty_count = 0
            for row in rows[:max_check]:
                val = str(row.get(col_name, "")).strip()
                if not val or val.lower() in ('none', 'null', 'nan', ''):
                    empty_count += 1
                else:
                    values.append(val)
            
            total_checked = min(len(rows), max_check)
            if total_checked == 0:
                return 'empty', {}
            
            fill_rate = len(values) / total_checked
            if fill_rate < 0.1:
                return 'empty', {'fill_rate': fill_rate}
            
            # تحليل خصائص القيم
            numeric_count = 0
            url_count = 0
            long_count = 0
            bool_count = 0
            timestamp_count = 0
            
            lengths = []
            for v in values:
                lengths.append(len(v))
                # أرقام بحتة (بما في ذلك الأسعار والأرقام العشرية)
                clean_v = v.replace(',', '').replace(' ', '')
                if regex_module.match(r'^-?[\d.]+$', clean_v):
                    numeric_count += 1
                    # طابع زمني Unix (13 رقم)
                    if clean_v.isdigit() and len(clean_v) >= 10:
                        timestamp_count += 1
                # روابط
                if v.startswith(('http://', 'https://', 'www.', 'ftp://')):
                    url_count += 1
                # نصوص طويلة
                if len(v) > 80:
                    long_count += 1
                # منطقي
                if v.lower() in ('true', 'false', 'yes', 'no', 'نعم', 'لا', '0', '1'):
                    bool_count += 1
            
            n = len(values)
            avg_len = sum(lengths) / n if n else 0
            unique_vals = set(values)
            uniqueness_ratio = len(unique_vals) / n if n else 0
            
            stats = {
                'fill_rate': fill_rate,
                'unique_count': len(unique_vals),
                'total_non_empty': n,
                'avg_length': avg_len,
                'uniqueness_ratio': uniqueness_ratio,
            }
            
            # قواعد التصنيف (بالترتيب من الأعلى أولوية)
            if timestamp_count / n > 0.7:
                return 'timestamp', stats
            if numeric_count / n > 0.8:
                return 'numeric', stats
            if url_count / n > 0.5:
                return 'url', stats
            if bool_count / n > 0.7:
                return 'boolean', stats
            if avg_len > 80 or long_count / n > 0.4:
                return 'long_text', stats
            # معرفات فريدة (UUID, أكواد SKU) — نسبة فريدة عالية جداً
            if uniqueness_ratio > 0.9 and n > 5:
                return 'identifier', stats
            
            return 'categorical', stats
        
        # تصنيف جميع الأعمدة
        column_classifications = {}
        for col_name in active_cols:
            col_type, col_stats = classify_column(col_name, analysis_sample)
            column_classifications[col_name] = {
                'type': col_type,
                **col_stats
            }
        
        # ═══════════════════════════════════════════════════════════════
        # 2.2 — اكتشاف عمود الفئة الرئيسية (Category Column)
        # ═══════════════════════════════════════════════════════════════
        
        # كلمات مفتاحية مرتبة حسب الأولوية للفئات
        category_priority_keywords = [
            "فئة", "قسم", "تصنيف", "category", "section", "department", "group", "مجموعة",
            "type", "نوع", "class"
        ]
        # كلمات مفتاحية للماركات
        brand_keywords = [
            "ماركة", "براند", "brand", "العلامة", "الشركة المصنعة", "manufacturer", "maker"
        ]
        
        category_column = None
        brand_column = None
        categories_found = {}
        brands_found = {}
        
        # الخطوة 1: البحث في الأعمدة التصنيفية فقط
        categorical_cols = {
            name: info for name, info in column_classifications.items()
            if info['type'] == 'categorical'
        }
        
        def score_category_candidate(col_name, stats):
            """
            تسجيل نقاط لعمود مرشح كفئة. أعلى نقاط = أفضل مرشح.
            المعايير:
            - عدد القيم الفريدة معقول (2-200)
            - نسبة التعبئة عالية
            - متوسط طول القيمة قصير-متوسط (2-50 حرف)
            - نسبة التكرار جيدة (كل قيمة تتكرر عدة مرات)
            """
            score = 0
            unique = stats.get('unique_count', 0)
            fill = stats.get('fill_rate', 0)
            avg_len = stats.get('avg_length', 0)
            total = stats.get('total_non_empty', 0)
            uniqueness = stats.get('uniqueness_ratio', 1)
            
            # عدد القيم الفريدة مثالي (2-200)
            if unique < 2:
                return -100  # غير صالح
            if 2 <= unique <= 15:
                score += 30  # مثالي جداً
            elif 16 <= unique <= 50:
                score += 25
            elif 51 <= unique <= 200:
                score += 15
            else:
                score -= 20  # كثير جداً
            
            # نسبة التعبئة
            score += fill * 20
            
            # متوسط الطول (الفئات عادة 3-40 حرف)
            if 2 <= avg_len <= 40:
                score += 20
            elif 40 < avg_len <= 60:
                score += 10
            else:
                score -= 10
            
            # نسبة التكرار (الفئات تتكرر — ليست فريدة)
            if uniqueness < 0.3:
                score += 25  # تكرار عالي = فئة ممتازة
            elif uniqueness < 0.5:
                score += 15
            elif uniqueness < 0.7:
                score += 5
            else:
                score -= 15  # كل قيمة فريدة = ليست فئة
            
            return score
        
        # مرحلة 1: البحث بالكلمات المفتاحية أولاً (أعلى دقة)
        keyword_category_candidates = []
        keyword_brand_candidates = []
        
        for col_name, info in categorical_cols.items():
            col_lower = col_name.lower().strip()
            
            # فحص الفئة
            for kw in category_priority_keywords:
                if kw in col_lower:
                    s = score_category_candidate(col_name, info)
                    if s > 0:
                        keyword_category_candidates.append((col_name, s + 50))  # مكافأة الكلمة المفتاحية
                    break
            
            # فحص الماركة
            for kw in brand_keywords:
                if kw in col_lower:
                    s = score_category_candidate(col_name, info)
                    if s > 0:
                        keyword_brand_candidates.append((col_name, s + 50))
                    break
        
        # مرحلة 2: التحليل الإحصائي لباقي الأعمدة التصنيفية (بدون كلمات مفتاحية)
        statistical_candidates = []
        already_matched = set(c[0] for c in keyword_category_candidates + keyword_brand_candidates)
        
        for col_name, info in categorical_cols.items():
            if col_name in already_matched:
                continue
            s = score_category_candidate(col_name, info)
            if s > 10:
                statistical_candidates.append((col_name, s))
        
        # ترتيب حسب النقاط
        keyword_category_candidates.sort(key=lambda x: x[1], reverse=True)
        keyword_brand_candidates.sort(key=lambda x: x[1], reverse=True)
        statistical_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # اختيار عمود الفئة الأفضل
        if keyword_category_candidates:
            category_column = keyword_category_candidates[0][0]
        elif statistical_candidates:
            category_column = statistical_candidates[0][0]
        
        # اختيار عمود الماركة (مختلف عن الفئة)
        if keyword_brand_candidates:
            brand_column = keyword_brand_candidates[0][0]
            if brand_column == category_column and len(keyword_brand_candidates) > 1:
                brand_column = keyword_brand_candidates[1][0]
            elif brand_column == category_column:
                brand_column = None
        elif statistical_candidates:
            # البحث عن ثاني أفضل عمود تصنيفي كعمود ماركة محتمل
            for cand_name, cand_score in statistical_candidates:
                if cand_name != category_column:
                    col_lower = cand_name.lower()
                    # تفضيل الأعمدة التي تشبه أسماء الماركات
                    if any(bkw in col_lower for bkw in ["brand", "ماركة", "براند", "model", "موديل"]):
                        brand_column = cand_name
                        break
        
        # ═══════════════════════════════════════════════════════════════
        # 2.3 — استخراج الفئات والماركات الحقيقية (باستخدام Counter - O(n))
        # ═══════════════════════════════════════════════════════════════
        
        if category_column:
            cat_counter = Counter()
            for row in products_raw:
                val = str(row.get(category_column, "")).strip()
                if val and val.lower() not in ('none', 'null', 'nan', ''):
                    cat_counter[val] += 1
            
            if len(cat_counter) > 50:
                # أخذ أهم 50 فئة + تجميع الباقي
                categories_found = dict(cat_counter.most_common(50))
                other_count = sum(count for _, count in cat_counter.most_common()[50:])
                if other_count > 0:
                    categories_found["فئات أخرى..."] = other_count
            elif len(cat_counter) > 0:
                categories_found = dict(cat_counter)
        
        if brand_column:
            brand_counter = Counter()
            for row in products_raw:
                val = str(row.get(brand_column, "")).strip()
                if val and val.lower() not in ('none', 'null', 'nan', ''):
                    brand_counter[val] += 1
            
            if len(brand_counter) > 30:
                brands_found = dict(brand_counter.most_common(30))
                other_brand_count = sum(count for _, count in brand_counter.most_common()[30:])
                if other_brand_count > 0:
                    brands_found["ماركات أخرى..."] = other_brand_count
            elif len(brand_counter) > 0:
                brands_found = dict(brand_counter)
        
        # ═══════════════════════════════════════════════════════════════
        # 2.4 — التحليل الذكي بالـ AI (يعمل دائماً عند غياب الفئات)
        #    يستخرج الفئات + الماركات من أسماء المنتجات مباشرة
        #    يتعامل مع الحالة الشائعة: عمود واحد يحتوي الاسم+الماركة+الفئة
        # ═══════════════════════════════════════════════════════════════
        
        # نحتاج تحليل AI إذا:
        # 1. لا توجد فئات مكتشفة أصلاً
        # 2. أو الفئات المكتشفة هي أرقام/قيم غير مفيدة
        needs_ai_analysis = not categories_found and total_items > 5
        
        # فحص جودة الفئات المكتشفة (هل هي أرقام؟ هل هي قيم فارغة؟)
        if categories_found and not needs_ai_analysis:
            numeric_cats = sum(1 for cat in categories_found.keys() if str(cat).replace('.', '').replace('-', '').isdigit())
            if numeric_cats > len(categories_found) * 0.5:
                # أكثر من 50% من الفئات أرقام = خطأ في الاكتشاف
                categories_found = {}
                category_column = None
                needs_ai_analysis = True
        
        if needs_ai_analysis:
            # البحث عن عمود الاسم الأفضل
            name_col = None
            for col_name in active_cols:
                if any(kw in col_name.lower() for kw in ["اسم", "name", "منتج", "service", "عنوان", "title", "product", "item"]):
                    name_col = col_name
                    break
            if not name_col and active_cols:
                # أخذ أول عمود تصنيفي غير رقمي
                for col_name in active_cols:
                    info = column_classifications.get(col_name, {})
                    if info.get('type') in ('categorical', 'long_text'):
                        name_col = col_name
                        break
                if not name_col:
                    name_col = active_cols[0]
            
            if name_col:
                # ── أخذ عينة متنوعة وذكية من كل أنحاء قاعدة البيانات ──
                # نأخذ عينات من 5 شرائح: البداية، الربع الأول، الوسط، الربع الثالث، النهاية
                sample_indices = []
                if total_items <= 80:
                    sample_indices = list(range(total_items))
                else:
                    chunk_size = 16
                    positions = [0, total_items // 4, total_items // 2, 3 * total_items // 4, total_items - chunk_size]
                    for pos in positions:
                        sample_indices.extend(range(pos, min(pos + chunk_size, total_items)))
                    sample_indices = sorted(set(sample_indices))
                
                # استخراج الأسماء (مع معلومات إضافية من أعمدة أخرى إن وجدت)
                names_sample = []
                for idx in sample_indices:
                    if idx < len(products_raw):
                        row = products_raw[idx]
                        name_val = str(row.get(name_col, "")).strip()
                        if name_val and name_val.lower() not in ('none', 'null', 'nan', ''):
                            # إضافة معلومات من أعمدة أخرى قصيرة (مثل حجم، لون، إلخ) لتحسين التصنيف
                            extra_info = []
                            for other_col in active_cols:
                                if other_col == name_col:
                                    continue
                                col_info = column_classifications.get(other_col, {})
                                if col_info.get('type') == 'categorical' and col_info.get('avg_length', 100) < 30:
                                    other_val = str(row.get(other_col, "")).strip()
                                    if other_val and other_val.lower() not in ('none', 'null', 'nan', '') and len(other_val) < 30:
                                        extra_info.append(f"{other_col}:{other_val}")
                            
                            full_entry = name_val
                            if extra_info:
                                full_entry += f" [{', '.join(extra_info[:3])}]"
                            names_sample.append(full_entry)
                
                names_sample = names_sample[:80]  # حد أقصى 80 عنصر
                
                if names_sample:
                    clustering_prompt = f"""أنت خبير تصنيف منتجات ومحلل بيانات تجارية.

لدي متجر يحتوي على {total_items} منتج/خدمة. المعلومات قد تكون مدمجة في حقل واحد (الاسم يحتوي على الفئة والماركة معاً).

هذه عينة تمثيلية متنوعة من البيانات ({len(names_sample)} عنصر من أصل {total_items}):
{chr(10).join(f"{i+1}. {n}" for i, n in enumerate(names_sample))}

═══ المطلوب ═══

1. **الفئات**: صنّف هذه المنتجات في فئات منطقية (3-20 فئة حسب التنوع الحقيقي).
   - لا تختلق فئات لا أساس لها في البيانات.
   - لكل فئة، حدد كلمات بحث مفتاحية (3-5 كلمات) تساعد في البحث بقاعدة البيانات.

2. **الماركات/العلامات التجارية**: استخرج أي ماركات أو علامات تجارية مذكورة في الأسماء.
   - إذا لم تجد ماركات واضحة، اترك القائمة فارغة.

رد بتنسيق JSON حصراً بالشكل التالي:
{{
  "categories": {{"فئة1": ["كلمة_بحث1", "كلمة_بحث2"], "فئة2": ["كلمة_بحث1"]}},
  "brands": ["ماركة1", "ماركة2"]
}}
بدون أي نص إضافي خارج JSON."""
                    
                    try:
                        cluster_res = await get_ai_response(
                            client_id=user["id"],
                            user_message=clustering_prompt,
                            phone_number="CLUSTERING",
                            channel="system"
                        )
                        json_match = regex_module.search(r'\{.*\}', cluster_res.replace("\n", " "), regex_module.DOTALL)
                        if json_match:
                            ai_result = json.loads(json_match.group(0))
                            
                            # استخراج الفئات
                            ai_categories = ai_result.get("categories", ai_result)
                            if isinstance(ai_categories, dict):
                                for cat, keywords in ai_categories.items():
                                    if isinstance(keywords, list):
                                        categories_found[cat] = keywords
                                    else:
                                        categories_found[cat] = [str(keywords)]
                            
                            # استخراج الماركات
                            ai_brands = ai_result.get("brands", [])
                            if isinstance(ai_brands, list) and ai_brands and not brands_found:
                                brands_found = {brand: "—" for brand in ai_brands if brand}
                                brand_column = "تحليل ذكي (من الأسماء)"
                            
                            if categories_found:
                                category_column = "تحليل ذكي (AI Clustering)"
                    except Exception as cluster_err:
                        print(f"[STRATEGY] AI clustering error: {cluster_err}")

        # ── سجل التحليل (للتشخيص) ──
        print(f"[STRATEGY] ═══ Column Analysis Summary ═══")
        for col_name, info in column_classifications.items():
            print(f"[STRATEGY]   {col_name}: type={info['type']}, unique={info.get('unique_count', '?')}, fill={info.get('fill_rate', '?'):.1%}")
        print(f"[STRATEGY] Category column: {category_column or 'NONE'} | Brand column: {brand_column or 'NONE'}")
        print(f"[STRATEGY] Categories found: {len(categories_found)} | Brands found: {len(brands_found)}")
        if categories_found:
            for cat in list(categories_found.keys())[:5]:
                val = categories_found[cat]
                if isinstance(val, int):
                    print(f"[STRATEGY]   Cat: {cat} = {val} items")
                else:
                    print(f"[STRATEGY]   Cat: {cat} = keywords: {val[:3]}")
        print(f"[STRATEGY] ═══════════════════════════════")

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
            cat_lines = [f"    • {cat}: {count} عنصر" if isinstance(count, int) else f"    • {cat}: (كلمات بحث: {', '.join(count)})" for cat, count in sorted(categories_found.items(), key=lambda x: x[1] if isinstance(x[1], int) else 0, reverse=True)]
            categories_text = f"""
## الفئات المُستخرجة من البيانات (عمود التصنيف: "{category_column or 'تحليل ذكي'}"):
{chr(10).join(cat_lines)}
"""
        else:
            categories_text = """
## لم يتم العثور على عمود تصنيف واضح.
- البيانات لا تحتوي على فئات/أقسام.
"""
        
        brands_text = ""
        if brands_found:
            brand_lines = []
            for brand, count in sorted(brands_found.items(), key=lambda x: x[1] if isinstance(x[1], int) else 0, reverse=True):
                if isinstance(count, int):
                    brand_lines.append(f"    • {brand}: {count} عنصر")
                else:
                    brand_lines.append(f"    • {brand}")
            brands_text = f"""
## الماركات المُستخرجة من البيانات (المصدر: "{brand_column or 'تحليل ذكي'}"):
{chr(10).join(brand_lines)}
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
• عمود الماركة المُكتشف: {brand_column or "لا يوجد"}
• عدد الفئات المكتشفة: {len(categories_found) if categories_found else 0}
• عدد الماركات المكتشفة: {len(brands_found) if brands_found else 0}
{categories_text}
{brands_text}

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
{"- **المخزون صغير (6 عناصر أو أقل)**: اكتب قانوناً يأمر الموظف بعرض جميع العناصر مباشرة كأزرار بدون فئات أو أسئلة." if total_items <= 6 else ""}
{"- **توجد فئات مكتشفة**: اكتب قانوناً يأمر الموظف بعرض الفئات أولاً كأزرار واضحة، ثم بعد اختيار الفئة يعرض المنتجات. اذكر أسماء الفئات حرفياً." if categories_found and total_items > 6 else ""}
{"- **لا توجد فئات واضحة والمخزون كبير**: اكتب قانوناً يأمر الموظف بطرح سؤال استكشافي واحد لفهم حاجة العميل." if not categories_found and total_items > 6 else ""}
{"- **توجد ماركات مكتشفة**: اكتب تعليمات لكيف يتعامل الموظف مع سؤال العميل عن ماركة معينة (مثلاً: إذا سأل عن نايكي، ابحث بكلمات البحث الخاصة بهذه الماركة)." if brands_found else ""}
- **اذكر أسماء الفئات الفعلية** (إن وجدت) ليستخدمها الموظف حرفياً.
- **اذكر أسماء الماركات** (إن وجدت) ليتمكن الموظف من الرد على "وش عندكم من ماركة X؟".
- **ملاحظة مهمة**: البيانات قد تكون مدمجة في عمود واحد (الاسم يحتوي الفئة والماركة). كلمات البحث المفتاحية المرفقة مع كل فئة هي المفتاح للعثور على المنتجات في القاعدة.

### 2. بروتوكول الأعمدة (ما يُعرض وما يُخفى):
- لكل عمود نشط، اكتب تعليمة واحدة (يُعرض تلقائياً أم عند الطلب فقط).
- الأعمدة الموقوفة يجب أن تُذكر بقانون "يُمنع ذكرها نهائياً".

### 3. خريطة البيانات الحية (Data Map):
- اكتب ملخصاً مضغوطاً لما يحتويه المتجر (الأنواع، نطاق الأسعار، الماركات، أنماط ملحوظة).
- هذا يمنع الموظف من الهلوسة لأنه سيعرف بالضبط ما لديه.

### 4. قوانين الجوهر الصارمة:
- قوانين خاصة بهذا المتجر تحديداً بناءً على طبيعة بياناته.
- قانون التعامل مع البحث: كيف يبحث الموظف في القاعدة (بكلمات البحث المفتاحية للفئات أو باسم الماركة أو باسم المنتج مباشرة).

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
                    auto_header += f"  • {cat} (كلمات البحث: {', '.join(val)})\n"
                else:
                    auto_header += f"  • {cat} ({val} عنصر)\n"
        
        if brands_found:
            auto_header += f"\n- الماركات المتاحة (المصدر: {brand_column or 'تحليل ذكي'}):\n"
            for brand, count in sorted(brands_found.items(), key=lambda x: x[1] if isinstance(x[1], int) else 0, reverse=True):
                if isinstance(count, int):
                    auto_header += f"  • {brand} ({count} عنصر)\n"
                else:
                    auto_header += f"  • {brand}\n"

        
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
                "categories": {k: (v if isinstance(v, int) else len(v)) for k, v in categories_found.items()},
                "brands_count": len(brands_found),
                "brand_column": brand_column,
                "brands": {k: (v if isinstance(v, int) else 0) for k, v in brands_found.items()},
                "column_types": {name: info['type'] for name, info in column_classifications.items()}

            }
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": f"فشل توليد الجوهر الاستراتيجي: {str(e)}"}

@router.get("/api/planning/columns")
async def api_get_columns(user: dict = Depends(verify_merchant)):
    """جلب أعمدة البيانات المزامنة مع إعدادات التدريب"""
    db = get_db_client()
    try:
        # الحل لتفادي نفاذ الذاكرة (OOM) في قواعد البيانات الضخمة (250k+):
        # نعتمد بشكل أساسي على ما تم حفظه في إعدادات التدريب سابقاً
        saved_res = await db.table("column_training").select("*").eq("client_id", user["id"]).execute_async()
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
                data_res = await db.table("merchant_manual_data").select("data").eq("client_id", user["id"]).single().execute_async()
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
        
        insert_data = []
        for col in payload.columns:
            insert_data.append({
                "client_id": user["id"],
                "column_name": col.column_name,
                "note": col.note,
                "is_disabled": col.is_disabled,
                "on_request": col.on_request
            })
            
        if insert_data:
            db.table("column_training").insert(insert_data).execute()
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
async def api_update_business_rules(payload: dict, user: dict = Depends(verify_merchant)):
    """تحديث قواعد العمل"""
    db = get_db_client()
    try:
        existing = await db.table("business_rules").select("id").eq("client_id", user["id"]).execute_async()
        if existing.data:
            await db.table("business_rules").update({
                "rules_data": payload,
                "updated_at": datetime.now().isoformat()
            }).eq("client_id", user["id"]).execute_async()
        else:
            await db.table("business_rules").insert({
                "client_id": user["id"],
                "rules_data": payload,
                "updated_at": datetime.now().isoformat()
            }).execute_async()
        return {"status": "success", "message": "تم تحديث قواعد العمل بنجاح"}
    except Exception as e:
        return {"status": "error", "message": f"حدث خطأ: {str(e)}"}

@router.post("/api/business-rules/payment")
async def api_update_payment_settings(payload: dict, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات الدفع والضريبة فقط (دمج مع القواعد الموجودة)"""
    db = get_db_client()
    try:
        res = await db.table("business_rules").select("rules_data").eq("client_id", user["id"]).single().execute_async()
        current_rules = res.data.get("rules_data", {}) if res.data else {}
        for k, v in payload.items():
            current_rules[k] = v
        existing = await db.table("business_rules").select("id").eq("client_id", user["id"]).execute_async()
        if existing.data:
            await db.table("business_rules").update({
                "rules_data": current_rules,
                "updated_at": datetime.now().isoformat()
            }).eq("client_id", user["id"]).execute_async()
        else:
            await db.table("business_rules").insert({
                "client_id": user["id"],
                "rules_data": current_rules,
                "updated_at": datetime.now().isoformat()
            }).execute_async()
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
            await db.table("merchant_manual_data").delete().eq("client_id", user["id"]).execute_async()
        except:
            pass
            
        await db.table("merchant_manual_data").insert({
            "client_id": user["id"],
            "data": json.loads(data_json),
            "filename": filename,
            "updated_at": datetime.now().isoformat()
        }).execute_async()
        
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
    from database.db_client import run_in_db_thread
    # تنفيذ جميع الاستعلامات بالتوازي في مجمع الخيوط المخصص (4x أسرع)
    channels_config, numbers, allow_all, ignore_groups = await asyncio.gather(
        run_in_db_thread(get_channels_config, user["id"]),
        run_in_db_thread(get_authorized_numbers, user["id"]),
        run_in_db_thread(get_allow_all_status, user["id"]),
        run_in_db_thread(get_ignore_groups_status, user["id"]),
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
    from database.db_client import run_in_db_thread
    success = await run_in_db_thread(update_channels_config, user["id"], payload.model_dump())
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
async def api_add_authorized_number(payload: AuthorizedNumberRequest, user: dict = Depends(verify_merchant)):
    """إضافة رقم جديد"""
    success = await asyncio.to_thread(add_authorized_number, user["id"], payload.phone_number, payload.label)
    if success:
        return {"status": "success", "message": "تم إضافة الرقم بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الإضافة"}

@router.delete("/api/authorized-numbers/{record_id}")
async def api_delete_authorized_number(record_id: str, user: dict = Depends(verify_merchant)):
    """حذف رقم"""
    success = await asyncio.to_thread(delete_authorized_number, user["id"], record_id)
    if success:
        return {"status": "success", "message": "تم حذف الرقم بنجاح"}
    return {"status": "error", "message": "حدث خطأ أثناء الحذف"}

@router.post("/api/authorized-numbers/settings")
async def api_update_authorized_settings(payload: dict, user: dict = Depends(verify_merchant)):
    """تحديث إعدادات الأرقام والمجموعات"""
    from merchant.authorized_numbers import set_allow_all, set_ignore_groups
    
    if "allow_all" in payload:
        await asyncio.to_thread(set_allow_all, user["id"], payload["allow_all"])
    
    if "ignore_groups" in payload:
        await asyncio.to_thread(set_ignore_groups, user["id"], payload["ignore_groups"])
        
    return {"status": "success", "message": "تم تحديث الإعدادات بنجاح"}

class ClearMemoryRequest(BaseModel):
    phone_number: str

@router.post("/api/clear-memory")
async def api_clear_customer_memory(payload: ClearMemoryRequest, user: dict = Depends(verify_merchant)):
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
        res = await db.table("message_logs").delete().eq("client_id", user["id"]).or_(or_filter).execute_async()
        
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
async def api_get_data_view(user: dict = Depends(verify_merchant)):
    """جلب البيانات المزامنة للعرض"""
    db = get_db_client()
    try:
        # جلب البيانات اليدوية (Excel/CSV)
        data_res = await db.table("merchant_manual_data").select("data, filename").eq("client_id", user["id"]).single().execute_async()
        if data_res.data and data_res.data.get("data"):
            rows = data_res.data["data"]
            if isinstance(rows, str):
                try:
                    rows = json.loads(rows)
                except:
                    rows = []
            return {"status": "ok", "data": rows, "source_type": "excel"}

        # جلب إعدادات المزامنة لمعرفة المصدر
        sync_res = await db.table("sync_config").select("source_type").eq("client_id", user["id"]).single().execute_async()
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
    from database.db_client import run_in_db_thread
    # تنفيذ الاستعلامين بالتوازي في مجمع الخيوط المخصص
    orders, rules = await asyncio.gather(
        run_in_db_thread(_fetch_orders),
        run_in_db_thread(_fetch_rules),
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
async def api_create_order(payload: dict, user: dict = Depends(verify_merchant)):
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
        await db.table("orders").insert(order_data).execute_async()
        return {"status": "success", "message": "تم إنشاء الطلب بنجاح", "order_number": order_num}
    except Exception as e:
        print(f"Error creating order: {e}")
        return {"status": "error", "message": str(e)}

@router.put("/api/orders/{order_id}/status")
async def api_update_order_status(order_id: str, payload: dict, user: dict = Depends(verify_merchant)):
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
        
        await db.table("orders").update(update).eq("id", order_id).eq("client_id", user["id"]).execute_async()
        return {"status": "success", "message": "تم تحديث الحالة"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@router.delete("/api/orders/{order_id}")
async def api_delete_order(order_id: str, user: dict = Depends(verify_merchant)):
    """حذف طلب"""
    db = get_db_client()
    try:
        await db.table("orders").delete().eq("id", order_id).eq("client_id", user["id"]).execute_async()
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
async def api_get_insights(user: dict = Depends(verify_merchant)):
    """جلب آخر رؤى تم توليدها"""
    from merchant.insights import get_latest_insights
    try:
        data = await asyncio.to_thread(get_latest_insights, user["id"])
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
    
    def _create_tables():
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

    from database.db_client import run_in_db_thread
    await run_in_db_thread(_create_tables)
    
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
    from database.db_client import run_in_db_thread
    customers = await run_in_db_thread(get_all_customers, user["id"])
    planning = user["_planning"]
    return templates.TemplateResponse("merchant/customers.html", {
        "request": request, "user": user, "customers": customers, "planning": planning
    })

@router.get("/api/customers")
async def api_get_customers(user: dict = Depends(verify_merchant)):
    """جلب جميع العملاء كـ JSON"""
    from merchant.customers.customer_manager import get_all_customers
    customers = await asyncio.to_thread(get_all_customers, user["id"])
    return {"status": "success", "customers": customers}

@router.put("/api/customers/{customer_id}")
async def api_update_customer(customer_id: str, payload: dict, user: dict = Depends(verify_merchant)):
    """تحديث بيانات عميل"""
    from merchant.customers.customer_manager import update_customer_data
    db = get_db_client()
    try:
        # جلب المعرف الرئيسي للعميل
        res = await db.table("customer_profiles").select("platform_identifier").eq("id", customer_id).eq("client_id", user["id"]).single().execute_async()
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
async def api_delete_customer(customer_id: str, user: dict = Depends(verify_merchant)):
    """حذف عميل"""
    from merchant.customers.customer_manager import delete_customer
    success = await asyncio.to_thread(delete_customer, user["id"], customer_id)
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
            await db.table("message_logs").delete().eq("client_id", user["id"]).eq("phone_number", test_phone).execute_async()
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
