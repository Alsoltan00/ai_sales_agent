import os
import json
import httpx
from datetime import datetime
from database.db_client import get_supabase_client


def get_routing_matrix(delivery_type: str, channel: str) -> dict:
    """
    مصفوفة توجيه الطلبات الديناميكية.
    تُحدد البيانات التي تُسحب تلقائياً vs البيانات المطلوب طلبها من العميل
    بناءً على نوع المنتج (رقمي/حقيقي) والمنصة (واتساب/تيليجرام/انستقرام/تيك توك).
    """
    is_digital = (delivery_type == "digital")
    platform = "whatsapp"  # default
    if channel.startswith("whatsapp"):
        platform = "whatsapp"
    elif channel == "telegram":
        platform = "telegram"
    elif channel == "instagram":
        platform = "instagram"
    elif channel == "tiktok":
        platform = "tiktok"

    matrix = {
        "platform": platform,
        "is_digital": is_digital,
        "auto_pulled": [],       # بيانات تُسحب تلقائياً ولا تُطلب
        "required_fields": [],   # بيانات يجب طلبها من العميل
        "forbidden_fields": [],  # بيانات يُمنع طلبها نهائياً
    }

    # ── البيانات المسحوبة تلقائياً حسب المنصة ──
    if platform == "whatsapp":
        matrix["auto_pulled"] = ["رقم الهاتف"]
    elif platform in ("tiktok", "instagram"):
        matrix["auto_pulled"] = ["اليوزرنيم"]
    elif platform == "telegram":
        matrix["auto_pulled"] = ["معرف تيليجرام"]

    # ── البيانات المطلوبة حسب نوع المنتج + المنصة ──
    if is_digital:
        # رقمي: فقط طريقة الدفع (لجميع المنصات)
        matrix["required_fields"] = ["طريقة الدفع"]
        matrix["forbidden_fields"] = ["العنوان", "المدينة", "سعر الشحن"]
        # لا نحتاج الاسم ولا العنوان للمنتجات الرقمية
        if platform != "whatsapp":
            # المنصات الأخرى لا نملك رقم الهاتف لكن لسنا بحاجته للرقمي
            matrix["forbidden_fields"].append("رقم الهاتف")
    else:
        # حقيقي: البيانات تختلف حسب المنصة
        if platform == "whatsapp":
            matrix["required_fields"] = ["الاسم", "العنوان", "طريقة الدفع"]
            # رقم الهاتف مسحوب تلقائياً
        elif platform in ("tiktok", "instagram"):
            matrix["required_fields"] = ["رقم الهاتف", "الاسم", "العنوان", "طريقة الدفع"]
        elif platform == "telegram":
            matrix["required_fields"] = ["رقم الهاتف", "الاسم", "العنوان", "طريقة الدفع"]
        else:
            matrix["required_fields"] = ["رقم الهاتف", "الاسم", "العنوان", "طريقة الدفع"]

    return matrix



async def get_ai_response(client_id: str, phone_number: str, user_message: str,
                          image_base64: str = None, audio_base64: str = None,
                          message_id: str = None, channel: str = "whatsapp"):
    """
    High-Precision AI Engine v4.0
    - Strict data injection from DB (no hallucination)
    - Full error logging for diagnosis
    - Correct OR query support
    """
    supabase = get_supabase_client()

    # ─── 1. MERCHANT IDENTITY ────────────────────────────────────────────────
    client_res = supabase.table("clients").select("*").eq("id", client_id).single().execute()
    if not client_res.data:
        print(f"[ENGINE] ERROR: Client {client_id} not found.")
        return "عذراً، المتجر غير موجود."

    c = client_res.data
    agent_name  = c.get("agent_name", "نوره")
    company_name = c.get("company_name", "المتجر")
    store_activity = c.get("store_activity", "تجارة")
    description = c.get("description", "")
    base_tone   = c.get("ai_tone", "حماسي وتسويقي")
    messages_used = c.get("messages_used", 0)
    message_limit = c.get("message_limit", 1000)

    if messages_used >= message_limit:
        return "نعتذر، انتهى رصيد الرسائل للمتجر."

    print(f"[ENGINE] Client: {company_name} | Agent: {agent_name} | Provider TBD")

    # ─── 1.5 CUSTOMER PROFILE LOOKUP (CRM) ───────────────────────────────
    customer_context = ""
    try:
        from merchant.customers.customer_manager import get_or_create_customer
        # تنظيف المعرف الرئيسي
        clean_identifier = phone_number.split("@")[0].replace("+", "")
        platform = "whatsapp" if channel.startswith("whatsapp") else channel
        
        customer = get_or_create_customer(client_id, platform, clean_identifier, clean_identifier if platform.startswith("whatsapp") else None)
        
        if customer:
            c_name = customer.get("customer_name") or ""
            c_addr = customer.get("customer_address") or ""
            c_city = customer.get("customer_city") or ""
            c_phone = customer.get("phone_number") or ""
            c_orders = customer.get("total_orders", 0)
            
            if c_name or c_addr:
                customer_context = f"""\n## بيانات العميل الحالي (معروف لدينا مسبقاً):
- اسم العميل: {c_name if c_name else 'غير معروف (يجب سؤاله)'}
- العنوان: {c_addr if c_addr else 'غير معروف (يجب سؤاله)'}
- المدينة: {c_city if c_city else 'غير معروفة'}
- رقم الهاتف: {c_phone if c_phone else 'غير معروف'}
- عدد الطلبات السابقة: {c_orders}
**تعليمات:** إذا كان اسم العميل معروفاً، ناده باسمه بود ولا تسأله عن اسمه مرة أخرى. إذا كان العنوان معروفاً وقرر الشراء، اعرض عليه عنوانه السابق للتأكيد بدلاً من طلبه من جديد. إذا كانت البيانات غير معروفة، اطلبها منه عند إتمام الطلب."""
                print(f"[ENGINE] Customer CRM data injected: {c_name or 'NEW'}")
            else:
                customer_context = "\n## بيانات العميل الحالي: عميل جديد (لا توجد بيانات سابقة). يجب طلب الاسم والعنوان عند إتمام الطلب."
                print(f"[ENGINE] New customer: {clean_identifier}")
    except Exception as e:
        print(f"[ENGINE] Customer CRM lookup error: {e}")

    # ─── 2. AI MODEL RESOLUTION ──────────────────────────────────────────────
    api_key, model_id, provider = None, "gpt-3.5-turbo", "openai"
    try:
        # A. Check plan-assigned model first
        plan_name = c.get("subscription_plan")
        if plan_name:
            p_det = supabase.table("subscription_plans").select("permissions").eq("name", plan_name).single().execute()
            if p_det.data:
                perms = p_det.data.get("permissions", {})
                if isinstance(perms, str): perms = json.loads(perms)
                mid = perms.get("assigned_model_id")
                if mid:
                    gm = supabase.table("global_ai_models").select("*").eq("id", mid).single().execute()
                    if gm.data:
                        api_key  = gm.data["api_key"]
                        model_id = gm.data["model_id"]
                        provider = gm.data["provider"].lower()

        # B. Fallback: merchant's own active config
        if not api_key:
            m_cfg = supabase.table("ai_models_config").select("*").eq("client_id", client_id).eq("is_active", True).execute()
            if m_cfg.data:
                api_key  = m_cfg.data[0]["api_key"]
                model_id = m_cfg.data[0]["model_id"]
                provider = m_cfg.data[0]["provider"].lower()

        if not api_key:
            print(f"[ENGINE] ERROR: No active API key found for client {client_id}")
            return "عذراً، لم يتم إعداد نموذج الذكاء الاصطناعي للمتجر."

    except Exception as e:
        print(f"[ENGINE] Model resolution error: {e}")


    # ─── 3. COLUMN TRAINING → BEHAVIORAL RULES + DATA FILTERS ────────────────
    col_behavior_rules = ""
    restricted_columns = set()   # أعمدة "عند الطلب" — تُخفى من البيانات
    disabled_columns   = set()   # أعمدة "إيقاف" — يتجاهلها النموذج كلياً

    try:
        col_res = supabase.table("column_training") \
            .select("column_name, note, is_disabled, on_request") \
            .eq("client_id", client_id).execute()

        if col_res.data:
            rules_list = []
            for item in col_res.data:
                col        = item.get("column_name", "").strip()
                note       = (item.get("note") or "").strip()
                is_disabled = item.get("is_disabled", False)
                on_request  = item.get("on_request", False)

                if not col:
                    continue

                if is_disabled:
                    disabled_columns.add(col)
                    # لا نُضيف للـ rules — النموذج لن يراها أصلاً

                elif on_request:
                    restricted_columns.add(col)
                    rules_list.append(
                        f"- [{col}]: هذا الحقل سري ويُعطى فقط إذا طلبه العميل صراحةً بكلمات واضحة."
                    )

                elif note:
                    rules_list.append(f"- [{col}]: {note}")

            if rules_list:
                col_behavior_rules = (
                    "## تعليمات إلزامية لكل حقل من حقول البيانات:\n"
                    + "\n".join(rules_list)
                )
            print(f"[ENGINE] Disabled cols: {disabled_columns} | On-request cols: {restricted_columns}")
    except Exception as e:
        print(f"[ENGINE] Column training error: {e}")

    # ─── 4. CONVERSATION HISTORY (Context Extraction) ───────────────────────────
    history = []
    # التنظيف للبحث الشامل: إزالة أي لواحق مثل @s.whatsapp.net أو :1 للأجهزة المرتبطة
    clean_p = phone_number.replace("+", "").split("@")[0].split(":")[0]
    if clean_p.startswith("00"): clean_p = clean_p[2:]
    
    # مصفوفة الاحتمالات لضمان جلب الذاكرة مهما كان تنسيق الرقم المخزن
    v_search = [clean_p, f"{clean_p}@s.whatsapp.net", f"+{clean_p}", f"00{clean_p}"]
    or_filter = ",".join([f"phone_number.eq.{x}" for x in v_search])
    recent_context_text = ""

    try:
        # Fetch last 8 exchanges ordered by time ascending
        h_res = supabase.table("message_logs") \
            .select("message_text, ai_response") \
            .or_(or_filter) \
            .eq("client_id", client_id) \
            .order("timestamp", desc=True) \
            .limit(8) \
            .execute()

        if h_res.data:
            # Enrich keywords from the most recent 2 exchanges
            recent_exchanges = h_res.data[:2]
            for msg in recent_exchanges:
                recent_context_text += f" {msg.get('message_text', '')} {msg.get('ai_response', '')}"
                
            for m in reversed(h_res.data):
                u = (m.get("message_text") or "").strip()
                a = (m.get("ai_response") or "").strip()
                if u: history.append({"role": "user",      "content": u})
                if a: history.append({"role": "assistant", "content": a})
            print(f"[ENGINE] History loaded: {len(history)} messages")
        else:
            print(f"[ENGINE] No history for {clean_p}")
    except Exception as e:
        print(f"[ENGINE] History error: {e}")

    # ─── 5. PRODUCT DATA (Smart Context-Aware Search) ─────────────────────────
    product_section = ""
    try:
        data_res = supabase.table("merchant_manual_data").select("data").eq("client_id", client_id).execute()
        if data_res.data and data_res.data[0].get("data"):
            all_rows = data_res.data[0]["data"]
            total = len(all_rows)
            print(f"[ENGINE] Total products in DB: {total}")

            # ── إزالة التكرارات: نستخدم بصمة نصية لكل صف ──
            seen_fingerprints = set()
            unique_rows = []
            for row in all_rows:
                # بناء بصمة من القيم الأساسية (تجاهل المفاتيح التقنية)
                fp_parts = []
                for k, v in row.items():
                    v_str = str(v).strip().lower()
                    if v_str.isdigit() and len(v_str) >= 13:  # تجاهل timestamps
                        continue
                    if k in disabled_columns:
                        continue
                    fp_parts.append(v_str)
                fingerprint = "|".join(sorted(fp_parts))
                if fingerprint not in seen_fingerprints:
                    seen_fingerprints.add(fingerprint)
                    unique_rows.append(row)
            
            dedup_removed = total - len(unique_rows)
            if dedup_removed > 0:
                print(f"[ENGINE] Deduplication: removed {dedup_removed} duplicate rows")
            all_rows = unique_rows

            # Extract keywords from user message AND recent context (≥2 chars)
            combined_text = recent_context_text + " " + user_message
            # تجاهل الكلمات العامة جداً التي لا تفيد في البحث
            stop_words = {'ماذا', 'لديك', 'لديكم', 'عندك', 'عندكم', 'اعطني', 'اعطيني', 'ابغى', 'ابي', 'اريد', 'اختيارات', 'خيارات', 'ايش', 'وش', 'شنو', 'عرض', 'اعرض', 'قائمة', 'منتجات', 'خدمات', 'الكل', 'كل', 'جميع', 'شو', 'هل', 'في', 'من', 'على', 'مع', 'عن', 'الى', 'هذا', 'هذه', 'ذلك', 'تلك', 'لي', 'لك', 'ان', 'اذا', 'يا', 'او', 'كيف', 'متى', 'اين', 'لماذا', 'هنا'}
            keywords = [k.strip() for k in combined_text.replace("؟","").replace("?","").split() if len(k.strip()) >= 2 and k.strip().lower() not in stop_words]
            
            # Remove duplicate keywords
            keywords = list(set(keywords))

            # Score rows by keyword relevance
            scored = []
            for row in all_rows:
                row_text = " ".join(str(v) for v in row.values()).lower()
                score = sum(1 for kw in keywords if kw.lower() in row_text)
                scored.append((score, row))

            # Sort: matched rows first, then rest
            scored.sort(key=lambda x: x[0], reverse=True)

            # Take top 15 relevant + up to 5 general (تقليل العدد لمنع الهلوسة)
            relevant = [r for s, r in scored if s > 0][:15]
            general  = [r for s, r in scored if s == 0][:5]
            final_rows = relevant + general

            print(f"[ENGINE] Matched rows: {len(relevant)} | General fill: {len(general)}")

            # Build clean readable lines — apply column filters
            lines = []
            for row in final_rows:
                parts = []
                for k, v in row.items():
                    v_str = str(v)
                    # 1. حذف الطوابع الزمنية (Unix timestamps — 13 رقماً)
                    if v_str.isdigit() and len(v_str) >= 13:
                        continue
                    # 2. حذف الأعمدة الموقوفة (is_disabled) كلياً
                    if k in disabled_columns:
                        continue
                    # 3. حذف الأعمدة "عند الطلب" — لا يراها النموذج إلا عند الطلب
                    if k in restricted_columns:
                        continue
                    parts.append(f"{k}: {v}")
                if parts:
                    lines.append("• " + " | ".join(parts))

            if lines:
                tag = "✅ نتائج مطابقة لطلبك:\n" if relevant else ""
                product_section = tag + "\n".join(lines)
                print(f"[ENGINE] Restricted columns hidden from AI: {restricted_columns}")
            else:
                product_section = "لا توجد منتجات مسجلة."
        else:
            print(f"[ENGINE] No product data found for client {client_id}")
            product_section = "لا توجد منتجات مسجلة حالياً."
    except Exception as e:
        print(f"[ENGINE] Product data error: {e}")
        product_section = "تعذّر تحميل قائمة المنتجات."

    # ─── 6. BUSINESS RULES ────────────────────────────────────────────────────
    rules_section = ""
    item_term = "العناصر"
    single_item_term = "العنصر"
    try:
        r_res = supabase.table("business_rules").select("rules_data").eq("client_id", client_id).single().execute()
        if r_res.data and r_res.data.get("rules_data"):
            rd = r_res.data["rules_data"]
            
            # Dynamic Activity Terms
            act_type = rd.get("activity_type", "products")
            if act_type == "products":
                item_term = "المنتجات"
                single_item_term = "المنتج"
            elif act_type == "services":
                item_term = "الخدمات"
                single_item_term = "الخدمة"
            elif act_type == "bookings":
                item_term = "المواعيد والحجوزات"
                single_item_term = "الموعد أو الحجز"
            elif act_type == "other":
                custom_val = rd.get("custom_activity_type", "").strip()
                item_term = custom_val if custom_val else "العناصر"
                single_item_term = custom_val if custom_val else "العنصر"
            else:
                item_term = "العناصر"
                single_item_term = "العنصر"

            checkout_type = rd.get("checkout_type", "store")

            if checkout_type == "chat":
                payments = []
                if rd.get("chat_payment_cod"):      payments.append("الدفع عند الاستلام (COD)")
                if rd.get("chat_payment_transfer"): payments.append(f"تحويل بنكي — {rd.get('bank_accounts','')}")
                if rd.get("chat_payment_link"):     payments.append(f"رابط دفع — {rd.get('payment_links','')}")
                checkout_rule = f"إتمام الطلب داخل الواتساب. طرق الدفع: {', '.join(payments) or 'حسب الاتفاق'}."
                
                # إعدادات إكمال الطلب (Cart Behavior)
                cart_behavior = rd.get("chat_cart_behavior", "ask_more")
                confirm_type  = rd.get("chat_confirmation", "summary")
                
                if cart_behavior == "close_fast":
                    order_rule = "بمجرد تحديد العميل لطلبه، انتقل مباشرة لتنفيذ (بروتوكول إتمام الطلب) المذكور في القواعد السفلية لتأكيد العنوان وعرض الملخص النهائي."
                else:
                    order_rule = f"بعد أن يطلب العميل {single_item_term}، اسأله: 'هل ترغب بإضافة شيء آخر؟'. إذا اختار 'إضافة عنصر آخر ➕'، اطلب منه تحديد الـ {single_item_term} الإضافي الذي يريده. ويُمنع منعاً باتاً أن تقوم بزيادة كمية طلبه السابق أو تكراره من تلقاء نفسك. أما إذا اختار 'إتمام الطلب 🛒'، فانتقل فوراً لتنفيذ (بروتوكول إتمام الطلب) المذكور في القواعد لجمع البيانات وعرض الملخص."
            else:
                checkout_rule = f"وجّه العميل لإتمام الشراء عبر رابط {single_item_term}."
                order_rule    = f"لا تطلب بيانات العميل، فقط أرسل الرابط."

            rules_section = f"""
## دستور العمل (التزم به حرفياً):
- **مسار الطلب:** {checkout_rule}
- **إتمام البيع:** {order_rule}
- **الخصومات:** {rd.get('discount_msg', 'لا توجد خصومات حالية.')}
- **الشكاوى:** {rd.get('complaint_msg', 'أبدِ تعاطفاً وأبلغ الإدارة.')}
"""
    except Exception as e:
        print(f"[ENGINE] Business rules error: {e}")

    # ─── 6.5 DELIVERY TYPE + ROUTING MATRIX + CUSTOM INSTRUCTIONS ─────────────────
    is_digital = False
    custom_instructions = ""
    ai_temperature = 0.1
    ai_max_tokens = 600
    order_flow = "in_chat"
    routing = {}
    try:
        from merchant.planning.planning_config import get_planning_config
        p_cfg = get_planning_config(client_id)
        delivery_type = p_cfg.get("delivery_type", "physical")
        order_flow = p_cfg.get("order_flow", "in_chat")
        if delivery_type == "digital":
            is_digital = True
            print(f"[ENGINE] Digital product detected — shipping disabled")
        # بناء مصفوفة التوجيه الديناميكية
        routing = get_routing_matrix(delivery_type, channel)
        print(f"[ENGINE] Routing Matrix: platform={routing['platform']}, auto={routing['auto_pulled']}, required={routing['required_fields']}, forbidden={routing['forbidden_fields']}")
        custom_instructions = (p_cfg.get("custom_instructions") or "").strip()
        ai_temperature = float(p_cfg.get("ai_temperature") or 0.1)
        ai_max_tokens = int(p_cfg.get("ai_max_tokens") or 600)
        print(f"[ENGINE] Model params: temp={ai_temperature}, max_tokens={ai_max_tokens}, order_flow={order_flow}")
    except Exception as e:
        print(f"[ENGINE] Planning config error: {e}")
        routing = get_routing_matrix("physical", channel)  # fallback

    # ─── 6.6 SHIPPING DATA + ROUTING RULES ─────────────────────────────────────
    shipping_section = ""
    routing_section = ""

    # بناء تعليمات التوجيه الديناميكية بناءً على المصفوفة
    if routing:
        auto_text = "، ".join(routing.get("auto_pulled", []))
        req_text = "، ".join(routing.get("required_fields", []))
        forbidden_text = "، ".join(routing.get("forbidden_fields", []))
        platform_name = {"whatsapp": "واتساب", "telegram": "تيليجرام", "instagram": "انستقرام", "tiktok": "تيك توك"}.get(routing.get("platform", ""), "غير معروفة")

        routing_section = f"""
## مصفوفة توجيه البيانات (قانون صارم — المنصة: {platform_name}):
- **بيانات مسحوبة تلقائياً (لا تطلبها أبداً):** {auto_text or 'لا يوجد'}
- **بيانات يجب طلبها من العميل لإتمام الطلب:** {req_text or 'لا يوجد'}
- **بيانات محظور طلبها نهائياً:** {forbidden_text or 'لا يوجد'}
- **تحذير صارم:** يُمنع منعاً باتاً طلب أي بيانات مذكورة في (المسحوبة تلقائياً) أو (المحظورة).
- **قانون الإلزام المطلق:** لا يجوز لك إطلاقاً الانتقال لعرض الملخص أو إنشاء الفاتورة ما لم تكن قد جمعت **كل** (البيانات التي يجب طلبها) حرفياً من العميل. إذا قدم العميل بعضها وتجاهل الآخر (مثلاً أعطاك العنوان ولم يعطك الاسم)، **توقف فوراً** واطلب منه استكمال الناقص (الاسم) قبل إتمام الطلب.
"""

    if is_digital:
        shipping_section = """
## سياسة التوصيل:
- **هذا المتجر يقدم منتجات/خدمات رقمية فقط — لا يوجد توصيل أو شحن.**
- **يُمنع منعاً باتاً** طلب عنوان العميل أو مدينته أو أي بيانات شحن.
- **يُمنع** إضافة أي تكلفة شحن أو ذكر كلمة "شحن" أو "توصيل" في أي رد.
- عند إتمام الطلب: التزم حصرياً بالبيانات المذكورة في (مصفوفة توجيه البيانات) أعلاه.
"""
    if not is_digital:
        try:
            ship_cfg = supabase.table("shipping_config").select("*").eq("client_id", client_id).single().execute()
            ship_zones_res = supabase.table("shipping_zones").select("zone_name, shipping_price, free_shipping_enabled, free_shipping_min").eq("client_id", client_id).execute()
            ship_zones = ship_zones_res.data or []

            if ship_cfg.data or ship_zones:
                sc = ship_cfg.data or {}
                unavail_msg = sc.get("unavailable_area_msg", "")

                zones_text = ""
                if ship_zones:
                    zones_list = []
                    for z in ship_zones:
                        price = float(z.get("shipping_price", 0))
                        free_enabled = z.get("free_shipping_enabled", False)
                        free_min = float(z.get("free_shipping_min", 0))
                        
                        line = f"  - {z['zone_name']}: {price} \u0631\u064a\u0627\u0644"
                        if price == 0:
                            line = f"  - {z['zone_name']}: \u0645\u062c\u0627\u0646\u064a"
                        if free_enabled and free_min > 0:
                            line += f" (\u0634\u062d\u0646 \u0645\u062c\u0627\u0646\u064a \u0639\u0646\u062f \u062a\u062c\u0627\u0648\u0632 \u0627\u0644\u0637\u0644\u0628 {free_min} \u0631\u064a\u0627\u0644)"
                        zones_list.append(line)
                    zones_text = "\n".join(zones_list)

                shipping_section = f"""
## \u0633\u064a\u0627\u0633\u0629 \u0627\u0644\u0634\u062d\u0646 (\u0627\u0644\u062a\u0632\u0645 \u0628\u0647\u0627 \u062d\u0631\u0641\u064a\u0627\u064b):
- \u0645\u0646\u0627\u0637\u0642 \u0627\u0644\u0634\u062d\u0646 \u0627\u0644\u0645\u062a\u0627\u062d\u0629 \u0648\u0623\u0633\u0639\u0627\u0631\u0647\u0627:
{zones_text}
- **\u0625\u0630\u0627 \u0630\u0643\u0631 \u0627\u0644\u0639\u0645\u064a\u0644 \u0645\u062f\u064a\u0646\u0629 \u0623\u0648 \u0645\u0646\u0637\u0642\u0629 \u063a\u064a\u0631 \u0645\u0648\u062c\u0648\u062f\u0629 \u0641\u064a \u0627\u0644\u0642\u0627\u0626\u0645\u0629 \u0623\u0639\u0644\u0627\u0647:** {unavail_msg if unavail_msg else '\u0623\u062e\u0628\u0631\u0647 \u0628\u0644\u0637\u0641 \u0623\u0646 \u0627\u0644\u0634\u062d\u0646 \u063a\u064a\u0631 \u0645\u062a\u0627\u062d \u062d\u0627\u0644\u064a\u0627\u064b \u0644\u0645\u0646\u0637\u0642\u062a\u0647 \u0648\u0633\u064a\u062a\u0645 \u062a\u062d\u0648\u064a\u0644 \u0637\u0644\u0628\u0647 \u0644\u0644\u0625\u062f\u0627\u0631\u0629.'}
- **\u062a\u062d\u0630\u064a\u0631 \u0635\u0627\u0631\u0645:** \u064a\u064f\u0645\u0646\u0639 \u0645\u0646\u0639\u0627\u064b \u0628\u0627\u062a\u0627\u064b \u0627\u0641\u062a\u0631\u0627\u0636 \u0623\u0648 \u062a\u062e\u0645\u064a\u0646 \u0633\u0639\u0631 \u0627\u0644\u0634\u062d\u0646 \u0625\u0630\u0627 \u0644\u0645 \u064a\u062e\u0628\u0631\u0643 \u0627\u0644\u0639\u0645\u064a\u0644 \u0628\u0645\u062f\u064a\u0646\u062a\u0647. \u064a\u062c\u0628 \u0623\u0646 \u062a\u0633\u0623\u0644\u0647 \u0639\u0646 \u0645\u062f\u064a\u0646\u062a\u0647 \u0623\u0648\u0644\u0627\u064b \u0644\u062a\u0639\u0631\u0641 \u0633\u0639\u0631 \u0627\u0644\u0634\u062d\u0646 \u0627\u0644\u0635\u062d\u064a\u062d.
- \u0639\u0646\u062f \u062d\u0633\u0627\u0628 \u0627\u0644\u0641\u0627\u062a\u0648\u0631\u0629 \u0627\u0644\u0646\u0647\u0627\u0626\u064a\u0629 (\u0641\u0642\u0637 \u0628\u0639\u062f \u0645\u0639\u0631\u0641\u0629 \u0627\u0644\u0645\u062f\u064a\u0646\u0629)\u060c \u0623\u0636\u0641 \u0633\u0639\u0631 \u0627\u0644\u0634\u062d\u0646 \u0628\u0646\u0627\u0621\u064b \u0639\u0644\u0649 \u0645\u062f\u064a\u0646\u0629 \u0627\u0644\u0639\u0645\u064a\u0644 \u0648\u0623\u0638\u0647\u0631\u0647 \u0643\u0628\u0646\u062f \u0645\u0646\u0641\u0635\u0644 \u0641\u064a \u0627\u0644\u0645\u0644\u062e\u0635. \u0625\u0630\u0627 \u0643\u0627\u0646 \u0627\u0644\u0634\u062d\u0646 \u0645\u062c\u0627\u0646\u064a (\u0628\u0633\u0628\u0628 \u062a\u062c\u0627\u0648\u0632 \u0627\u0644\u062d\u062f \u0627\u0644\u0623\u062f\u0646\u0649) \u0627\u0630\u0643\u0631 \u0630\u0644\u0643.
- \u0623\u0636\u0641 \u062d\u0642\u0644 "shipping_cost" \u0641\u064a ORDER_DATA \u0628\u0627\u0644\u0642\u064a\u0645\u0629 \u0627\u0644\u0635\u062d\u064a\u062d\u0629.
"""
                print(f"[ENGINE] Shipping zones loaded: {len(ship_zones)} zones")
        except Exception as e:
            print(f"[ENGINE] Shipping data error: {e}")

    # ─── 7. FINAL SYSTEM PROMPT ───────────────────────────────────────────────
    # تعليمات المنصة الديناميكية بناءً على مصفوفة التوجيه
    platform_key = routing.get("platform", "whatsapp") if routing else "whatsapp"
    if platform_key == "whatsapp":
        phone_instruction = "لا تطلب رقم الجوال أبداً، وتجاهله من متطلبات البيانات (لأننا نتحدث عبر الواتساب ورقم هاتفه معروف لدينا تلقائياً)."
    elif platform_key == "telegram":
        if is_digital:
            phone_instruction = "معرف تيليجرام الخاص بالعميل معروف لدينا تلقائياً. لا تطلب رقم هاتفه لأن المنتج رقمي."
        else:
            phone_instruction = "معرف تيليجرام الخاص بالعميل معروف لدينا تلقائياً، لكن يجب أن تطلب رقم الجوال للتواصل (هذا شرط إلزامي لأن المنتج يحتاج توصيل)."
    elif platform_key in ("instagram", "tiktok"):
        platform_ar = "انستقرام" if platform_key == "instagram" else "تيك توك"
        if is_digital:
            phone_instruction = f"يوزرنيم {platform_ar} الخاص بالعميل معروف لدينا تلقائياً. لا تطلب رقم هاتفه لأن المنتج رقمي."
        else:
            phone_instruction = f"يوزرنيم {platform_ar} الخاص بالعميل معروف لدينا تلقائياً، لكن يجب أن تطلب رقم الجوال + الاسم + العنوان لأن المنتج يحتاج توصيل."
    else:
        phone_instruction = "اطلب رقم الجوال للتواصل."
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    system_prompt = f"""تاريخ ووقت اليوم الحالي: {current_time}
أنت "{agent_name}"، موظف مبيعات محترف وذكي جداً في "{company_name}".
نشاط المتجر: {store_activity}.
{f'نبذة: {description}' if description else ''}
نبرة الصوت: {base_tone}.
{customer_context}

## الدستور الأعلى لفن المبيعات والتعامل مع العملاء:
هذا الدستور مصمم ليجعلك بائعاً محترفاً. اتبع هذه التكتيكات بصرامة شديدة مع كل عميل:

1. **الاستماع النشط واكتشاف الحاجة:**
   - لا ترمِ المنتجات في وجه العميل مباشرة! إذا كان طلب العميل عاماً، اطرح سؤالاً واحداً ذكياً لفهم مشكلته أو احتياجه الحقيقي أولاً.
2. **بيع الحلول وليس الميزات:**
   - عندما تقترح أي عنصر، لا تكتفِ بذكر اسمه وسعره فقط. اشرح باختصار شديد وودود **كيف سيحل هذا الشيء مشكلة العميل** أو يضيف له قيمة.
3. **خلق الرغبة:**
   - استخدم عبارات تضفي قيمة للمنتج مثل: "هذا من أكثر اختيارات عملائنا تميزاً"، أو "هذا الخيار عليه طلب عالي جداً".
4. **معالجة الاعتراضات:**
   - إذا اعترض العميل على السعر، استخدم تكتيك (التعاطف ثم القيمة). قل: "أتفهم شعورك تماماً، السعر قد يبدو مرتفعاً للوهلة الأولى، لكن الجودة العالية تجعله استثماراً ممتازاً." (تذكر: يمنع تقديم أي خصم).
5. **الإغلاق المزدوج (التخيير):**
   - لا تسأل العميل سؤالاً إجابته نعم/لا مثل "هل تريد الشراء؟". بل اسأله لتخييره بين أمرين من القائمة: "أيهما تفضل، [الخيار الأول] أم [الخيار الثاني]؟".
6. **البيع المتقاطع الذكي:**
   - إذا اختار العميل منتجاً، اقترح عليه منتجاً مكملاً من القائمة.
8. **استخدام البرهان الاجتماعي:**
   - لمّح بذكاء إلى أن المتجر نشط والناس يشترون منه. مثال: "هذا الموديل هو الأكثر طلباً هذا الأسبوع".
9. **قاعدة المعاملة بالمثل:**
   - قبل البيع، قدم قيمة بسيطة. إذا سأل العميل سؤالاً، أجبه بذكاء وأعطه نصيحة سريعة تتعلق بمجال نشاط المتجر لتكسب ثقته.
10. **التعامل مع التردد:**
    - إذا قال العميل "سأفكر" أو "سأعود لاحقاً"، قل: "بالتأكيد، خذ وقتك! لكن هل هناك شيء محدد يجعلك تتردد؟ هل هو السعر، أم المواصفات؟ أنا هنا لأساعدك في اتخاذ أفضل قرار."

11. **قواعد الشخصية والذاكرة:**
   - تحدث كإنسان طبيعي ودود، لا تذكر مصطلحات تقنية أبداً.
   - **فهم إجابات العميل الرقمية:** إذا طرحت على العميل سؤالاً بخيارات مرقمة (مثل 1- نعم، 2- لا، أو 1- موافق)، وأجاب العميل برقم (مثل "1")، فيجب عليك فوراً اعتبار إجابته موافقة صريحة على ذلك الخيار (مثل الموافقة على الطلب). يُمنع منعاً باتاً أن ترد عليه بـ "لا يوجد خيار رقم 1" أو تبحث عن منتج بهذا الرقم.
   - **منع تأليف الهويات:** أنت موظف مبيعات فقط ({agent_name}). إذا سُئلت عن "صاحب المتجر" اعتذر بلطف وأخبره أنك مجرد موظف ولا تملك هذه التفاصيل.
   - إذا سألك العميل "هل تعرف اسمي؟"، إن كان ذكره سابقاً فناده به بمزاح، وإن لم يذكره فاعتذر بلطف واطلبه.
   - لا تكرر التعريف بنفسك في كل رسالة.
   - **لا تقفز لطلب عنوان أو شحن** إلا عند إتمام الطلب الفعلي.
5. **حساب الإجمالي (دقة رياضية قصوى):** عند حساب إجمالي الطلب، يجب عليك ضرب سعر كل {single_item_term} في الكمية المطلوبة منه بدقة (السعر × الكمية). **تحذير:** يُمنع جمع أسعار الوحدات فقط وتجاهل الكمية. الإجمالي النهائي = (سعر الـ {single_item_term}1 × كميته) + (سعر الـ {single_item_term}2 × كميته){' + سعر الشحن' if not is_digital else ''}. اذكر الإجمالي بوضوح في الملخص.
6. **بروتوكول إتمام الطلب (تسلسل صارم يُمنع فيه دمج الخطوات في رسالة واحدة):**
   - **الخطوة 1 (جمع البيانات):** لا تعرض أي ملخص{'ولا تحسب إجمالي الشحن' if not is_digital else ''} بعد. أولاً وقبل كل شيء، راجع "بيانات العميل الحالي". إذا لم تكن جميع البيانات المطلوبة ({', '.join(routing.get('required_fields', ['طريقة الدفع']))}) متوفرة، يجب عليك سؤاله لجمع ما ينقص منها. **تحذير خطير:** يُمنع منعاً باتاً افتراض الاسم، أو تركه فارغاً، أو استخدام نصوص نائبة مثل `[اسم العميل]`{ ' أو `[عنوانك]`' if not is_digital else ''}. إذا كان العميل لم يخبرك باسمه، **توقف هنا واسأله (مثلاً: "فضلاً ما هو اسمك الكريم لتسجيل الطلب؟")**. لا تكمل أي خطوة أخرى ولا تعرض الإجمالي حتى يرد العميل ببياناته الحقيقية كاملة.
   - **الخطوة 2 (الملخص والمراجعة):** **فقط بعد** أن تكتمل جميع البيانات المطلوبة فعلياً من العميل ({', '.join(routing.get('required_fields', ['طريقة الدفع']))})، قم بعرض ملخص الطلب متضمناً: ({item_term}، الإجمالي{'، الشحن المحسوب لمدينته الحقيقية' if not is_digital else ''}، {', '.join(routing.get('required_fields', ['طريقة الدفع']))}). واسأله حصراً: "هل نعتمد الطلب بهذه البيانات؟". **توقف هنا! لا تضف وسم الفاتورة بعد.**
   - **الخطوة 3 (إنشاء الفاتورة):** **فقط بعد** أن يوافق العميل صراحة على الملخص المعروض في الخطوة 2 (كأن يقول "نعم" أو "1")، يجب أن ترفق بيانات الطلب كـ JSON داخل الوسم المغلق بالأقواس المربعة بالشكل التالي حصراً ليدعمه النظام: `[ORDER_DATA: {{"items": [{{"name":"...", "qty":1, "price":10.0}}], {('"shipping_cost":20.0, ' if not is_digital else '')}"total_amount":30.0, {('"customer_name":"[الاسم الذي كتبه العميل]", ' if 'الاسم' in routing.get('required_fields', []) else '')}{('"customer_address":"[العنوان الذي كتبه العميل]", ' if not is_digital else '')}"payment_method":"..."}}]` في نهاية الرد. **يُمنع منعاً باتاً إضافة وسم [ORDER_DATA] في الخطوتين 1 أو 2، أو تركه ببيانات وهمية.**
## ⛔ قانون عرض {item_term} (أهم قانون — كسره يُعتبر خطأ فادح):
**يُمنع منعاً باتاً ذكر أكثر من 4 عناصر في رد واحد مهما كان السبب.**
عندما يسأل العميل سؤالاً عاماً مثل: "ماذا لديك؟" أو "أعطني خيارات" أو "ايش عندكم؟":
1. **الترحيب والأسلوب:** يجب أن تبدأ دائماً بترحيب لبق ودافئ (مثال: "يا هلا بك! 🌟 يسعدنا خدمتك...") في أول مرة يسأل فيها العميل عن الخيارات.
2. **قاعدة الأقسام الذكية:** 
   - إذا كان إجمالي الـ {item_term} المتوفرة **كثيراً (أكثر من 6 عناصر)** ومصنفة تحت "أقسام" أو "فئات" واضحة: **يُمنع** سرد العناصر مباشرة. يجب عليك عرض "الأقسام" فقط كأزرار ليختار العميل قسماً معيناً أولاً.
   - إذا كان العدد **قليلاً (6 عناصر أو أقل)**، أو كانت جميعها تندرج تحت قسم واحد فقط: اعرض العناصر مباشرة كأزرار لتسهيل الطلب على العميل وتجنب إضاعة وقته في تصنيفات غير ضرورية.
3. **التفاعل عبر الأزرار:** يجب أن تكون الأزرار هي (أسماء الأقسام) في الحالة الأولى، أو (أسماء الـ {item_term}) في الحالة الثانية.
4. **الأولوية القصوى:** التزم بأي تعليمات خاصة في (واجهة التخطيط) بخصوص طريقة العرض، فهي تُلغي أي قاعدة عامة هنا.
5. **تحذير التكرار:** لا تكرر الترحيب إذا كان العميل قد رحبت به مسبقاً في نفس المحادثة، اجعل الرد منساباً.


## بروتوكول التعامل مع الطلبات المباشرة لـ {single_item_term} محدد (إلزامي):
إذا طلب العميل {single_item_term} بعينه أو سأل عن {single_item_term} محدد بالاسم (مثل "أريد صبغة كذا" أو "عندكم كذا؟") وكان متوفراً في القائمة:
1. **تجاوز خطوة الأقسام كلياً.** لا تسأله أي قسم يهمك.
2. أكد له فوراً أن الـ {single_item_term} متوفر.
3. اعرض له تفاصيل الـ {single_item_term} (الاسم + السعر + أي تفاصيل ضرورية كالحجم/اللون).
4. اسأله مباشرة عن الكمية التي يحتاجها.

## بروتوكول التعامل مع الفئات (عند تحديد قسم كامل):
عندما يحدد العميل فئة معينة وفي القائمة أكثر من خيار:
**الخطوة 1 — أذكر الخيارات المتاحة بشكل متميز لتجنب التكرار:**
حدد أقصى 3 خيارات مختلفة واسأل العميل أيهما يفضل. **قاعدة هامة:** إذا كانت الـ {item_term} تشترك في نفس الاسم ولكنها تختلف في ميزة معينة (مثل اللون، الحجم، أو النكهة)، يجب عليك دمج هذه الميزة مع الاسم في الخيار حتى يميز العميل بينها. **يُمنع منعاً باتاً تكرار نفس الجملة في الخيارات.**
مثال: "لدينا [اسم الـ {single_item_term} - الحجم/اللون الأول] و[اسم الـ {single_item_term} - الحجم/اللون الثاني]. أيهما يناسبك؟"

**الخطوة 2 — عرض التفاصيل بعد الاختيار:**
بعد أن يختار العميل، أعطه التفاصيل المحددة للـ {single_item_term} الذي اختاره (الاسم الكامل + السعر). واسأله عن الكمية المطلوبة.

## خطوات الفحص الإلزامية قبل تأكيد توفر أي شيء للعميل:
1. ابحث في (قائمة البيانات المتوفرة) عن طلب العميل.
2. إذا وجدت {single_item_term}، **يجب عليك أولاً مراجعة (تعليمات حقول البيانات) وتطبيقها حرفياً على هذا {single_item_term} تحديداً.**
3. إذا كانت التعليمات تطلب منك اعتباره "غير متوفر" بسبب قيمة معينة (مثل الكمية 0، أو محجوز)، فيجب عليك إخفاءه تماماً والرد كأنه غير موجود في القائمة أبداً، وتطبيق (قواعد تصنيف الأسئلة - الحالة 2).

{col_behavior_rules}

## قائمة البيانات المتوفرة ({item_term} - المصدر الوحيد للحقيقة):
{product_section}

{rules_section}

{shipping_section}

{routing_section}

## قوانين الحماية العالمية (صارمة جداً لجميع الأنشطة - لا يمكن كسرها أبداً):
1. **المساومة والأسعار:** يُمنع منعاً باتاً تغيير الأسعار المسجلة أو تقديم خصومات للعملاء مهما أصروا أو حاولوا المساومة. السعر نهائي كما هو مكتوب في البيانات. لا توافق على إعطاء أي شيء "مجاناً" ما لم يكن سعره (0) صراحةً.
2. **الكميات والمخزون (مقارنة رياضية صارمة):** عندما يطلب العميل كمية (رقم)، يجب عليك مقارنتها رياضياً مع الكمية المتوفرة في المخزون. **إذا كانت الكمية المطلوبة أقل من أو تساوي (<=) المتوفر، يجب عليك قبول الطلب فوراً**. أما إذا كانت الكمية المطلوبة أكبر من (>) المتوفر، اعتذر وأخبره بالمتوفر فقط. **استثناء:** إذا طلب العميل "الكمية كاملة" أو "أريدهم كلهم" لـ {single_item_term} محدد، فقم فوراً بتسجيل الطلب بالعدد الفعلي الموجود في المخزون لذلك الـ {single_item_term} فقط ولا ترفضه. إذا لم يحدد الكمية لـ {single_item_term} آخر، افترض أنها (1) حبة/مرة واحدة فقط.
3. **طرق الدفع المخترعة:** لا تقبل أبداً أي طريقة دفع يقترحها العميل (مثل العملات الرقمية، أو الدفع لاحقاً) إلا إذا كانت مطابقة حرفياً لطرق الدفع المذكورة في سياسة المتجر. إذا كانت غير مدعومة، ارفضها بلطف واعرض الطرق المتاحة.
4. **الخروج عن النص (Off-Topic):** إذا سألك العميل أسئلة عامة (معلومات عامة، برمجة، استشارات طبية، إلخ) أو بدأ بالفضفضة الشخصية، تفاعل بكلمتين تعاطف/لباقة كحد أقصى، ثم أعد توجيه المحادثة فوراً نحو {item_term} التي يقدمها المتجر. لا تلعب دور المستشار أبداً.
5. **الوعود الكاذبة:** لا تعد العميل بأي ميزات غير موجودة في البيانات (مثل: توصيل خلال ساعة، أو ضمان ذهبي) ما لم تكن مكتوبة بوضوح في النبذة أو الشحن.
6. **الاختصار وتجنب التكرار الممل (هام جداً):** إياك وتكرار اسم الـ {single_item_term} أو تفاصيله الطويلة أكثر من مرة واحدة في نفس الرسالة. اجمع المعلومات لـ {single_item_term} في جملة واحدة قصيرة ومباشرة (مثال: "تم اعتماد 1 من [اسم {single_item_term}]، السعر كذا"). لا تقسم الرد إلى فقرات وأسطر متعددة مكررة لنفس الـ {single_item_term}.
7. **تنسيق الأرقام والأسعار:** يجب عليك دائماً تقريب الأسعار وأي أرقام عشرية إلى خانتين فقط (مثلاً 9.75 ريال بدلاً من 9.74947). يُمنع منعاً باتاً كتابة أسعار بأرقام عشرية طويلة ومزعجة للعين.

## قانون منع الهلوسة والتأليف (صارم جداً وغير قابل للكسر):
- **سياسة الصفر المعرفي (Zero-Knowledge Policy):** تجاهل كل ما تعرفه عن هذا النوع من التجارة أو {item_term} من العالم الخارجي. المرجع الوحيد والحصري لك هو ما تم تزويدك به في (قائمة البيانات المتوفرة) فقط. إذا لم تكن المعلومة موجودة في البيانات هنا، فهي غير موجودة نهائياً بالنسبة لك ولا يجوز ذكرها.
- **المنع القطعي للتأليف:** لا تقم أبداً باختراع أو استنتاج أي {single_item_term} أو فئة من خيالك. يجب أن تستند ردودك بنسبة 100% حصرياً على ما هو مكتوب حرفياً في (قائمة البيانات المتوفرة) فقط.
- **تجاهل التوقعات:** حتى لو عرفت نشاط المتجر ({store_activity})، لا تفترض وجود {item_term} شائعة لهذا النشاط. إذا كان القائمة لا تحتوي على شيء محدد، فهو غير موجود.
- لا تكرر أي {single_item_term} أكثر من مرة واحدة في نفس الرد أبداً.
- لا تقترح بدائل من خارج القائمة. إذا سأل العميل عن شيء غير موجود، التزم فوراً بـ (قواعد تصنيف الأسئلة - الحالة 2).
- لا تذكر أي اسم تجاري أو ماركة إلا إذا كانت مكتوبة صراحةً في القائمة.
- المرجعيات الترتيبية: إذا قال العميل "الأول"، "الثاني"، احسب الترتيب حرفياً بناءً على ما ذكرته أنت في آخر رسالة.
- **الحد الأقصى المطلق:** لا تذكر أكثر من 3 عناصر في أي رد مهما كان السبب.

## قواعد تصنيف الأسئلة (إلزامية):

**الحالة 1 — سؤال خارج نطاق نشاط العمل تماماً:**
إذا سأل العميل عن شيء بعيد جداً عن نشاطكم ({store_activity}):
أخبره أن هذا الشيء خارج النشاط، ثم وضّح له النشاط الذي تقدمونه.
مثال: "أهلاً بك! بخصوص [الشيء الذي سأل عنه]، هذا خارج نطاق عملنا للأسف. نحن نشاطنا يحتوي على {store_activity}، هل يمكنني مساعدتك بشيء من {item_term} المتاحة لدينا؟ 🌟"

**الحالة 2 — {single_item_term} مقارب للنشاط لكنه غير متوفر في القائمة:**
إذا سأل العميل عن شيء يندرج ضمن النشاط أو مقارب له، ولكنه غير موجود في قائمة البيانات:
أخبره بلطف أنه غير متوفر حالياً، وأضف أنه **سيتم توفيره أو إتاحته في أقرب وقت**.
مثال: "أهلاً بك! بخصوص [الطلب]، للأسف غير متاح لدينا حالياً ولكن سيتم توفيره بأقرب وقت إن شاء الله. هل تبحث عن شيء آخر من {item_term} في الوقت الحالي؟ 🌟"

## بروتوكول الأزرار التفاعلية (إلزامي — لا تشرحه للعميل أبداً):
**في كل مرة** تعرض خيارات أو تسأل سؤالاً، يجب أن تضيف وسم الأزرار في **نهاية ردك تماماً**.
الصيغة: `[BUTTONS: نص الزر 1 | نص الزر 2 | نص الزر 3]`
قواعد:
- كل زر 20 حرفاً كحد أقصى.
- 2 أو 3 أزرار فقط.
- يجب أن تضيف الوسم في كل رد يتضمن سؤالاً أو خيارات. بدونه يعتبر ردك ناقصاً.
أمثلة إلزامية:
- عرض فئات: "لدينا [فئة 1] و[فئة 2]" → [BUTTONS: فئة 1 | فئة 2]
- سؤال إضافات: "هل تريد إضافة شيء آخر؟" → [BUTTONS: إضافة عنصر آخر ➕ | إتمام الطلب 🛒]
- عرض خيارين: "[خيار 1] أو [خيار 2]؟" → [BUTTONS: خيار 1 | خيار 2]
- موافقة على الطلب: "هل البيانات صحيحة؟" → [BUTTONS: نعم، أوافق ✅ | تعديل ✏️]
"""

    # ─── 7.1 CUSTOM INSTRUCTIONS LAYER (Merchant-specific) ────────────────────
    if custom_instructions:
        system_prompt += f"""\n\n## تعليمات مخصصة من صاحب المتجر (أولوية قصوى — التزم بها حرفياً):\n{custom_instructions}\n"""

    # ─── 8. BUILD MESSAGE PAYLOAD ─────────────────────────────────────────────
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)

    if image_base64:
        messages.append({"role": "user", "content": [
            {"type": "text",      "text": user_message or "حلل هذه الصورة"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
        ]})
    else:
        messages.append({"role": "user", "content": user_message})

    print(f"[ENGINE] Sending {len(messages)} messages to {provider}/{model_id}")

    # ─── 9. LLM CALL (With Retry Logic) ──────────────────────────────────────
    import asyncio
    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            if   provider == "openai":     response = await _call_openai(api_key, model_id, messages, ai_temperature, ai_max_tokens)
            elif provider == "google":     response = await _call_google(api_key, model_id, messages, system_prompt, ai_temperature, ai_max_tokens)
            elif provider == "openrouter": response = await _call_openrouter(api_key, model_id, messages, ai_temperature, ai_max_tokens)
            elif provider == "groq":       response = await _call_groq(api_key, model_id, messages, ai_temperature, ai_max_tokens)
            elif provider == "anthropic":  response = await _call_anthropic(api_key, model_id, messages, system_prompt, ai_temperature, ai_max_tokens)
            elif provider == "huggingface": response = await _call_huggingface(api_key, model_id, messages, ai_temperature, ai_max_tokens)
            elif provider == "cerebras":    response = await _call_cerebras(api_key, model_id, messages, ai_temperature, ai_max_tokens)
            elif provider == "nvidia":      response = await _call_nvidia(api_key, model_id, messages, ai_temperature, ai_max_tokens)
            else:
                response = await _call_openrouter(api_key, model_id, messages, ai_temperature, ai_max_tokens)

            _log_message(supabase, client_id, user_message, response, phone_number, channel, message_id)
            supabase.table("clients").update({"messages_used": messages_used + 1}).eq("id", client_id).execute()
            return response

        except Exception as e:
            err_msg = str(e)
            if ("429" in err_msg or "traffic" in err_msg.lower()) and attempt < max_retries:
                print(f"[ENGINE] Rate limit hit (attempt {attempt+1}), retrying in 2s...")
                await asyncio.sleep(2)
                continue
            
            print(f"[ENGINE] CRITICAL LLM ERROR [{provider}]: {e}")
            return f"عذراً، واجهت مشكلة تقنية بسبب ضغط الطلبات حالياً. يرجى المحاولة مرة أخرى بعد لحظات."



# ─── PROVIDER IMPLEMENTATIONS ─────────────────────────────────────────────────

async def _call_openai(api_key: str, model_id: str, messages: list, temperature: float = 0.1, max_tokens: int = 600) -> str:
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        )
        data = r.json()
        if "choices" not in data:
            raise Exception(f"OpenAI error: {data.get('error', {}).get('message', str(data))}")
        return data["choices"][0]["message"]["content"].strip()


async def _call_openrouter(api_key: str, model_id: str, messages: list, temperature: float = 0.1, max_tokens: int = 600) -> str:
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        )
        data = r.json()
        if "choices" not in data:
            raise Exception(f"OpenRouter error: {data.get('error', {}).get('message', str(data))}")
        return data["choices"][0]["message"]["content"].strip()


async def _call_groq(api_key: str, model_id: str, messages: list, temperature: float = 0.1, max_tokens: int = 600) -> str:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        )
        data = r.json()
        if "choices" not in data:
            raise Exception(f"Groq error: {data.get('error', {}).get('message', str(data))}")
        return data["choices"][0]["message"]["content"].strip()


async def _call_cerebras(api_key: str, model_id: str, messages: list, temperature: float = 0.1, max_tokens: int = 600) -> str:
    """استدعاء نماذج Cerebras السريعة جداً"""
    async with httpx.AsyncClient(timeout=45) as c:
        try:
            r = await c.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
            )
            
            # إذا فشل الطلب، نطبع السبب بالتفصيل في الكونسول للمطور
            if r.status_code != 200:
                print(f"[CEREBRAS ERROR] Status: {r.status_code}, Body: {r.text}")
                data = r.json() if "application/json" in r.headers.get("Content-Type", "") else {"error": r.text}
                raise Exception(f"Cerebras API Error ({r.status_code}): {data.get('error', {}).get('message', r.text)}")

            data = r.json()
            if "choices" not in data:
                raise Exception(f"Cerebras error: Unexpected response format: {str(data)}")
                
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[CEREBRAS EXCEPTION] {str(e)}")
            raise Exception(f"Cerebras Connection Error: {str(e)}")

async def _call_nvidia(api_key: str, model_id: str, messages: list, temperature: float = 0.1, max_tokens: int = 600) -> str:
    """استدعاء نماذج NVIDIA NIM (مثل Kimi K2.6) عبر OpenAI-compatible API"""
    async with httpx.AsyncClient(timeout=90) as c:
        try:
            r = await c.post(
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
            )

            if r.status_code != 200:
                print(f"[NVIDIA ERROR] Status: {r.status_code}, Body: {r.text}")
                data = r.json() if "application/json" in r.headers.get("Content-Type", "") else {"error": r.text}
                raise Exception(f"NVIDIA API Error ({r.status_code}): {data.get('error', {}).get('message', r.text)}")

            data = r.json()
            if "choices" not in data:
                raise Exception(f"NVIDIA error: Unexpected response format: {str(data)}")

            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[NVIDIA EXCEPTION] {str(e)}")
            raise Exception(f"NVIDIA Connection Error: {str(e)}")

async def _call_huggingface(api_key: str, model_id: str, messages: list, temperature: float = 0.1, max_tokens: int = 600) -> str:
    """استدعاء نماذج Hugging Face عبر Inference API"""
    async with httpx.AsyncClient(timeout=60) as c:
        try:
            r = await c.post(
                "https://api-inference.huggingface.co/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
            )
            data = r.json()
            if "choices" not in data:
                error_msg = data.get("error", str(data))
                if "currently loading" in str(error_msg):
                    raise Exception("النموذج قيد التحميل في Hugging Face، يرجى المحاولة بعد 30 ثانية.")
                raise Exception(f"HuggingFace error: {error_msg}")
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            raise Exception(f"HuggingFace Connection Error: {str(e)}")

async def _call_anthropic(api_key: str, model_id: str, messages: list, system: str, temperature: float = 0.1, max_tokens: int = 600) -> str:
    user_msgs = [m for m in messages if m["role"] != "system"]
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={"model": model_id, "system": system, "messages": user_msgs, "max_tokens": max_tokens, "temperature": temperature}
        )
        data = r.json()
        if "content" not in data:
            raise Exception(f"Anthropic error: {data.get('error', {}).get('message', str(data))}")
        return data["content"][0]["text"].strip()


async def _call_google(api_key: str, model_id: str, messages: list, system: str, temperature: float = 0.1, max_tokens: int = 600) -> str:
    m_id = model_id.strip()
    if not m_id.startswith("models/"):
        m_id = f"models/{m_id}"
    url = f"https://generativelanguage.googleapis.com/v1beta/{m_id}:generateContent?key={api_key}"

    contents = []
    for msg in messages:
        if msg["role"] == "system":
            continue
        role = "user" if msg["role"] == "user" else "model"
        parts = []
        if isinstance(msg["content"], str):
            parts = [{"text": msg["content"]}]
        elif isinstance(msg["content"], list):
            for p in msg["content"]:
                if p["type"] == "text":
                    parts.append({"text": p["text"]})
                elif p["type"] == "image_url":
                    b64 = p["image_url"]["url"].split(",")[-1]
                    parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
        contents.append({"role": role, "parts": parts})

    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": contents,
        "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}
    }
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(url, json=body)
        data = r.json()
        if r.status_code != 200:
            raise Exception(f"Google error: {data.get('error', {}).get('message', str(data))}")
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


# ─── LOGGING ──────────────────────────────────────────────────────────────────

def _log_message(supabase, client_id: str, user_msg: str, ai_res: str,
                 phone: str, channel: str, msg_id: str):
    try:
        supabase.table("message_logs").insert({
            "client_id":    client_id,
            "phone_number": phone,
            "message_text": user_msg,
            "ai_response":  ai_res,
            "channel":      channel,
            "message_id":   msg_id
        }).execute()
    except Exception as e:
        print(f"[ENGINE] Log error: {e}")