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
                          message_id: str = None, channel: str = "whatsapp",
                          base_url: str = None):
    """
    High-Precision AI Engine v4.0
    - Strict data injection from DB (no hallucination)
    - Full error logging for diagnosis
    - CRM-aware (Memory of past orders and invoice links)
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
    latest_invoice_link = ""
    if phone_number != "STRATEGY_GEN":
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
                
                # جلب آخر رابط فاتورة للعميل لتمكين الرد على "أعطني الرابط مجدداً"
                try:
                    order_res = supabase.table("orders").select("id").eq("client_id", client_id).eq("customer_phone", clean_identifier).order("created_at", desc=True).limit(1).execute()
                    if order_res.data and base_url:
                        latest_invoice_link = f"{base_url}/invoice/{order_res.data[0]['id']}"
                except: pass

                if c_name or c_addr or latest_invoice_link:
                    customer_context = f"""
## بيانات العميل الحالي (هذا العميل معروف لدينا مسبقاً):
- اسم العميل: {c_name if c_name else 'غير معروف'}
- رقم الهاتف: {c_phone if c_phone else 'غير معروف'}
- العنوان السابق: {c_addr if c_addr else 'غير معروف'}
- المدينة: {c_city if c_city else 'غير معروفة'}
- عدد الطلبات السابقة: {c_orders}
- رابط آخر فاتورة له: {latest_invoice_link if latest_invoice_link else 'لا يوجد حالياً'}

**تعليمات صارمة للتعامل مع هذا العميل (تجربة بشرية مخصصة):**
1. **الترحيب المخصص:** نظراً لأننا نعرف اسم العميل ({c_name})، خاطبه باسمه الأول بود وتلقائية منذ البداية (مثل: "أهلاً بك مرة أخرى يا {c_name}"). **يُمنع منعاً باتاً** سؤاله "ما هو اسمك؟" لأنك تعرفه بالفعل.
2. **روابط الفواتير:** إذا طلب العميل رابط فاتورته أو سأل "أين الفاتورة؟"، قم فوراً بتزويده بالرابط التالي: ({latest_invoice_link}) وأخبره أنها فاتورة آخر طلب له. **يُمنع** قول "ليس لدي صلاحية" أو "ستصلك لاحقاً" إذا كان الرابط موجوداً أعلاه.
3. **عند إتمام الطلب (Checkout):** إذا وصل العميل لمرحلة تسجيل الطلب، **يُمنع** أن تطلب منه إدخال بياناته من الصفر. بدلاً من ذلك، اعرض عليه بياناته السابقة المسجلة لدينا بوضوح (الاسم، رقم الهاتف، العنوان، المدينة).
4. **تأكيد البيانات:** قل له نصاً أو بأسلوبك: "هل نعتمد نفس بياناتك السابقة للشحن/التسجيل؟ (الاسم: {c_name}، العنوان: {c_addr}...) أم ترغب بتغييرها؟". 
5. **تحديث أو اعتماد:** إذا وافق، اعتمد هذه البيانات فوراً للطلب. إذا رغب بالتغيير، خذ منه البيانات الجديدة للطلب الحالي.
"""
                    print(f"[ENGINE] Customer CRM data injected: {c_name or 'NEW'} | Latest Link: {bool(latest_invoice_link)}")
                else:
                    customer_context = "\n## بيانات العميل الحالي: عميل جديد (لا توجد بيانات سابقة). عامله باحترافية واجمع بياناته (الاسم، العنوان، إلخ) عند مرحلة إتمام الطلب بشكل كامل."
                    print(f"[ENGINE] New customer: {clean_identifier}")
        except Exception as e:
            print(f"[ENGINE] Customer CRM lookup error: {e}")

    # ─── 2. AI MODEL RESOLUTION (Multi-Model Smart Router) ─────────────────────
    resolved_models = []  # قائمة النماذج المتاحة مرتبة بالأولوية
    try:
        # A. جلب النماذج المتعددة من الباقة
        plan_name = c.get("subscription_plan")
        if plan_name:
            p_det = supabase.table("subscription_plans").select("permissions, assigned_model_ids").eq("name", plan_name).single().execute()
            if p_det.data:
                perms = p_det.data.get("permissions", {})
                if isinstance(perms, str): perms = json.loads(perms)
                
                # أولاً: جلب النماذج المتعددة (الجديد)
                model_ids_list = p_det.data.get("assigned_model_ids") or []
                if isinstance(model_ids_list, str):
                    try: model_ids_list = json.loads(model_ids_list)
                    except: model_ids_list = []
                
                if model_ids_list:
                    # ترتيب حسب الأولوية
                    sorted_models = sorted(model_ids_list, key=lambda x: x.get("priority", 99))
                    for m_entry in sorted_models:
                        mid = m_entry.get("model_id")
                        if not mid:
                            continue
                        try:
                            gm = supabase.table("global_ai_models").select("*").eq("id", mid).single().execute()
                            if gm.data and gm.data.get("api_key"):
                                resolved_models.append({
                                    "api_key": gm.data["api_key"],
                                    "model_id": gm.data["model_id"],
                                    "provider": gm.data["provider"].lower(),
                                    "base_url": gm.data.get("base_url", ""),
                                    "name": gm.data.get("model_name", gm.data["model_id"]),
                                    "priority": m_entry.get("priority", 99)
                                })
                        except Exception as gm_err:
                            print(f"[ENGINE] Model {mid} fetch error: {gm_err}")
                
                # Fallback: النموذج القديم (assigned_model_id واحد)
                if not resolved_models:
                    mid = perms.get("assigned_model_id")
                    if mid:
                        gm = supabase.table("global_ai_models").select("*").eq("id", mid).single().execute()
                        if gm.data and gm.data.get("api_key"):
                            resolved_models.append({
                                "api_key": gm.data["api_key"],
                                "model_id": gm.data["model_id"],
                                "provider": gm.data["provider"].lower(),
                                "base_url": gm.data.get("base_url", ""),
                                "name": gm.data.get("model_name", gm.data["model_id"]),
                                "priority": 1
                            })

        # B. Fallback: إعداد التاجر المباشر
        if not resolved_models:
            m_cfg = supabase.table("ai_models_config").select("*").eq("client_id", client_id).eq("is_active", True).execute()
            if m_cfg.data:
                for cfg_item in m_cfg.data:
                    resolved_models.append({
                        "api_key": cfg_item["api_key"],
                        "model_id": cfg_item["model_id"],
                        "provider": cfg_item["provider"].lower(),
                        "base_url": cfg_item.get("base_url", ""),
                        "name": cfg_item.get("model_name", cfg_item["model_id"]),
                        "priority": len(resolved_models) + 1
                    })

        if not resolved_models:
            print(f"[ENGINE] ERROR: No active API key found for client {client_id}")
            return "عذراً، لم يتم إعداد نموذج الذكاء الاصطناعي للمتجر."

        # استخدام النموذج الأول كإعداد افتراضي للمتغيرات القديمة
        api_key = resolved_models[0]["api_key"]
        model_id = resolved_models[0]["model_id"]
        provider = resolved_models[0]["provider"]
        
        print(f"[ENGINE] Resolved {len(resolved_models)} models: {[m['name'] for m in resolved_models]}")

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
    recent_context_text = ""
    if phone_number != "STRATEGY_GEN":
        # التنظيف للبحث الشامل: إزالة أي لواحق مثل @s.whatsapp.net أو :1 للأجهزة المرتبطة
        clean_p = phone_number.replace("+", "").split("@")[0].split(":")[0]
        if clean_p.startswith("00"): clean_p = clean_p[2:]
        
        # مصفوفة الاحتمالات لضمان جلب الذاكرة مهما كان تنسيق الرقم المخزن
        v_search = [clean_p, f"{clean_p}@s.whatsapp.net", f"+{clean_p}", f"00{clean_p}"]
        or_filter = ",".join([f"phone_number.eq.{x}" for x in v_search])

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

    # ─── 4.5 PLANNING CONFIG + STRATEGY ──────────────────────────────────────
    is_digital = False
    custom_instructions = ""
    ai_core_strategy = ""
    ai_temperature = 0.1
    ai_max_tokens = 600
    order_flow = "in_chat"
    routing = {}
    try:
        from merchant.planning.planning_config import get_planning_config
        p_cfg = await get_planning_config(client_id)
        delivery_type = p_cfg.get("delivery_type", "physical")
        order_flow = p_cfg.get("order_flow", "in_chat")
        if delivery_type == "digital":
            is_digital = True
        
        # بناء مصفوفة التوجيه الديناميكية
        routing = get_routing_matrix(delivery_type, channel)
        custom_instructions = (p_cfg.get("custom_instructions") or "").strip()
        ai_core_strategy = (p_cfg.get("ai_core_strategy") or "").strip()
        ai_temperature = float(p_cfg.get("ai_temperature") or 0.1)
        ai_max_tokens = int(p_cfg.get("ai_max_tokens") or 600)
    except Exception as e:
        print(f"[ENGINE] Planning config error: {e}")
        routing = get_routing_matrix("physical", channel)  # fallback

    # ─── 5. PRODUCT DATA (Smart Context-Aware Search) ─────────────────────────
    product_section = ""
    if phone_number == "STRATEGY_GEN":
        product_section = "Products data is explicitly omitted during STRATEGY_GEN."
    else:
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
                
                # 🆕 تحسين: إذا كان هناك جوهر استراتيجي، نبحث عن كلمات البحث المفتاحية المرتبطة بالفئات المذكورة في رسالة المستخدم
                if ai_core_strategy:
                    import re
                    # البحث عن أنماط مثل: • اسم الفئة (كلمات البحث: كذا، كذا)
                    cat_matches = re.findall(r"•\s*([^(]+)\s*\(كلمات البحث:\s*([^)]+)\)", ai_core_strategy)
                    for cat_name, cat_kws in cat_matches:
                        cat_name_clean = cat_name.strip()
                        # إذا ذكر المستخدم اسم الفئة في رسالته
                        if cat_name_clean.lower() in combined_text.lower():
                            # إضافة كلمات البحث الخاصة بهذه الفئة
                            extra_kws = [ck.strip() for ck in cat_kws.split(",") if len(ck.strip()) >= 2]
                            keywords.extend(extra_kws)
                            print(f"[ENGINE] Smart category match: {cat_name_clean} -> Added keywords: {extra_kws}")

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

                # Take top 15 relevant
                relevant = [r for s, r in scored if s > 0][:15]
                
                # Smart Inventory Summary (المشكلة 4: رؤية المتجر بالكامل)
                # إذا لم يطلب العميل شيئاً محدداً (لا توجد كلمات بحث أو لا توجد نتائج)
                # يجب أن يرى النموذج أسماء *جميع* المنتجات ليعرف ماذا يملك، دون إرهاقه بالتفاصيل
                inventory_summary = []
                if not relevant:
                    # استخراج اسم المنتج من أول عمود (غالباً "الاسم" أو "المنتج")
                    for r in all_rows:
                        keys = list(r.keys())
                        if keys:
                            # نحاول إيجاد عمود اسمه يحتوي على 'اسم' أو 'name'، وإلا نأخذ أول عمود
                            name_key = next((k for k in keys if 'اسم' in k.lower() or 'name' in k.lower()), keys[0])
                            inventory_summary.append(str(r[name_key]))
                
                final_rows = relevant

                print(f"[ENGINE] Matched rows: {len(relevant)} | Full inventory extracted: {len(inventory_summary) > 0}")

                # Build clean readable lines for FULL DETAILS — apply column filters
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

                product_section = ""
                if lines:
                    product_section += "✅ المنتجات المطابقة لطلب العميل بالتفصيل:\n" + "\n".join(lines)
                
                if inventory_summary:
                    # فهرس مضغوط لجميع المنتجات (الأسماء فقط)
                    summary_text = "، ".join(inventory_summary)
                    product_section += f"\n\n📋 فهرس جميع {item_term} المتوفرة في المتجر (الأسماء فقط - اعرضها كأقسام أو أزرار كما ينص الدستور ولا تخترع غيرها):\n[{summary_text}]"
                    
                if not lines and not inventory_summary:
                    product_section = "لا توجد منتجات مسجلة."
                    
                print(f"[ENGINE] Restricted columns hidden from AI: {restricted_columns}")
            else:
                print(f"[ENGINE] No product data found for client {client_id}")
                product_section = "لا توجد منتجات مسجلة حالياً."
        except Exception as e:
            print(f"[ENGINE] Product data error: {e}")
            product_section = "تعذّر تحميل قائمة المنتجات."

    # ─── 6. BUSINESS RULES (قراءة شاملة لجميع إعدادات التاجر) ──────────────
    rules_section = ""
    item_term = "العناصر"
    single_item_term = "العنصر"
    merchant_policies = ""  # سياسات التاجر الديناميكية
    merchant_guardrails = ""  # حواجز الحماية
    try:
        r_res = supabase.table("business_rules").select("rules_data").eq("client_id", client_id).single().execute()
        if r_res.data and r_res.data.get("rules_data"):
            rd = r_res.data["rules_data"]
            
            # ── مصطلحات النشاط الديناميكية ──
            act_type = rd.get("activity_type", "")
            # fallback: إذا لم يُحدد في business_rules، نستخدم sales_type من planning
            if not act_type:
                sales_type_map = {"products": "products", "services": "services", "reservations": "bookings"}
                act_type = sales_type_map.get(order_flow, "products") if order_flow != "in_chat" else "products"
            
            if act_type == "products":
                item_term, single_item_term = "المنتجات", "المنتج"
            elif act_type == "services":
                item_term, single_item_term = "الخدمات", "الخدمة"
            elif act_type in ("bookings", "reservations"):
                item_term, single_item_term = "المواعيد والحجوزات", "الموعد أو الحجز"
            elif act_type == "other":
                custom_val = rd.get("custom_activity_type", "").strip()
                item_term = custom_val if custom_val else "العناصر"
                single_item_term = custom_val if custom_val else "العنصر"

            # ── مسار الطلب (Checkout Flow) ──
            checkout_type = rd.get("checkout_type", "chat") if order_flow == "in_chat" else "store"

            if checkout_type == "chat":
                payments = []
                if rd.get("chat_payment_cod"):      payments.append("الدفع عند الاستلام (COD)")
                if rd.get("chat_payment_transfer"): payments.append(f"تحويل بنكي — {rd.get('bank_accounts','')}")
                if rd.get("chat_payment_link"):     payments.append(f"رابط دفع — {rd.get('payment_links','')}")
                checkout_rule = f"إتمام الطلب داخل المحادثة. طرق الدفع المتاحة: {', '.join(payments) or 'حسب الاتفاق'}."
                
                cart_behavior = rd.get("chat_cart_behavior", "ask_more")
                if cart_behavior == "close_fast":
                    order_rule = f"بمجرد تحديد العميل لطلبه، انتقل مباشرة لبروتوكول إتمام الطلب."
                else:
                    order_rule = f"بعد أن يطلب العميل {single_item_term}، اسأله: 'هل ترغب بإضافة شيء آخر؟' مع أزرار [إضافة عنصر آخر ➕ | إتمام الطلب 🛒]. يُمنع زيادة كمية طلبه السابق من تلقاء نفسك."
            else:
                checkout_rule = f"وجّه العميل لإتمام الشراء عبر رابط المتجر الإلكتروني."
                order_rule = f"لا تجمع بيانات العميل يدوياً، فقط أرسل رابط {single_item_term}."

            # ── سياسة الخصومات (كاملة) ──
            discount_type = rd.get("discount_type", "fixed")
            if discount_type == "fixed":
                d_pct = rd.get("discount_percent", "")
                d_thresh = rd.get("discount_threshold", "")
                if d_pct and d_thresh:
                    discount_rule = f"خصم {d_pct}% تلقائي عند تجاوز الفاتورة {d_thresh} ريال."
                else:
                    discount_rule = "لا توجد خصومات حالياً. الأسعار نهائية."
            elif discount_type == "code":
                discount_rule = f"وجّه العميل لاستخدام كود الخصم: {rd.get('discount_code', '')} في سلة المتجر."
            elif discount_type == "custom":
                discount_rule = rd.get("discount_custom", "لا توجد خصومات حالياً.")
            else:
                discount_rule = "لا توجد خصومات حالياً."
            discount_msg = rd.get("discount_msg", "")
            if discount_msg:
                discount_rule += f" الرسالة: {discount_msg}"

            # ── استراتيجية البيع (Upselling) ──
            upsell_type = rd.get("upsell_type", "none")
            if upsell_type == "cross":
                upsell_rule = f"بعد اختيار العميل لـ {single_item_term}، اقترح عليه بذكاء {single_item_term} مكمل من القائمة (Cross-sell)."
            elif upsell_type == "upgrade":
                upsell_rule = f"حاول بأسلوب لبق إقناع العميل بـ {single_item_term} ذي مواصفات أفضل وسعر أعلى (Upsell)."
            else:
                upsell_rule = f"لا تقترح إضافات. أجب على طلب العميل المباشر فقط."

            # ── سلوك نفاذ المخزون ──
            stock_out = rd.get("stock_out_type", "alternative")
            stock_out_msg = rd.get("stock_out_msg", "")
            if stock_out == "alternative":
                stock_rule = f"إذا طلب العميل شيئاً غير متوفر: اعتذر بلطف وابحث في نفس الفئة عن بدائل مشابهة واعرضها."
            elif stock_out == "collect_info":
                stock_rule = f"إذا طلب العميل شيئاً غير متوفر: اعتذر واطلب رقم هاتفه لإبلاغه عند توفره."
            else:
                stock_rule = f"إذا طلب العميل شيئاً غير متوفر: اعتذر بلطف فقط."
            if stock_out_msg:
                stock_rule = f"إذا طلب العميل شيئاً غير متوفر: '{stock_out_msg}'"

            # ── نقص التفاصيل ──
            details_missing = rd.get("details_missing_type", "static")
            if details_missing == "human":
                details_rule = "إذا سأل العميل عن تفصيل دقيق غير موجود في بياناتك: اعتذر بلباقة وأحل سؤاله للمختصين."
            else:
                static_info = rd.get("details_static_info", "")
                details_rule = f"إذا سأل العميل عن تفصيل دقيق غير موجود في بياناتك: أجب بـ '{static_info}'" if static_info else "إذا سأل عن تفصيل غير موجود: أخبره أن المعلومة غير متاحة حالياً."

            # ── سياسة الاسترجاع ──
            refund_type = rd.get("refund_type", "7days")
            if refund_type == "7days":
                refund_rule = "الاسترجاع والاستبدال متاح خلال 7-14 يوم بشرط عدم الاستخدام ووجود الفاتورة."
            elif refund_type == "exchange_only":
                refund_rule = "يُسمح بالاستبدال فقط (تغيير المقاس/اللون). لا يوجد استرجاع نقدي."
            elif refund_type == "none":
                refund_rule = "لا يوجد استرجاع أو استبدال نهائياً. جميع المبيعات نهائية."
            else:
                refund_rule = ""

            # ── الشكاوى ──
            complaint_type = rd.get("complaint_type", "discount")
            complaint_msg = rd.get("complaint_msg", "نعتذر عن هذه التجربة.")
            if complaint_type == "discount":
                complaint_code = rd.get("complaint_code", "")
                complaint_rule = f"عند شكوى العميل: تعاطف معه أولاً بقول '{complaint_msg}'" + (f" ثم قدم له كود ترضية: {complaint_code}" if complaint_code else "")
            elif complaint_type == "human":
                complaint_rule = f"عند شكوى العميل: قل '{complaint_msg}' ثم أحل المحادثة فوراً للقسم المختص."
            else:
                complaint_rule = f"عند شكوى العميل: '{complaint_msg}'"

            # ── صلاحية المكاسرة/التفاوض ──
            bargain_type = rd.get("bargain_type", "refuse")
            if bargain_type == "qty":
                bargain_qty = rd.get("bargain_qty", "")
                bargain_rule = f"إذا ساوم العميل على السعر: الأسعار نهائية للوحدة الواحدة، لكن يمكن تقديم خصم إذا تجاوزت الطلبية {bargain_qty} قطع."
            else:
                bargain_rule = "إذا ساوم العميل على السعر: ارفض بأدب ووضّح أن الأسعار نهائية ولا تقبل التفاوض."

            # ── حواجز الحماية (المواضيع الممنوعة) ──
            banned_topics = []
            if rd.get("ban_prices"): banned_topics.append("مقارنة أسعارنا بالمنافسين أو ذكر أي متجر آخر")
            if rd.get("ban_eta"): banned_topics.append("إعطاء وعود دقيقة بمواعيد وصول الشحنات")
            if rd.get("ban_general_chat"): banned_topics.append("الانجرار للأسئلة العامة والشخصية والفضفضة")
            if rd.get("ban_ai_admission"): banned_topics.append("الاعتراف بأنك ذكاء اصطناعي أو بوت — أنت موظف بشري فقط")
            ban_custom = rd.get("ban_custom", "").strip()
            if ban_custom: banned_topics.append(ban_custom)

            if banned_topics:
                merchant_guardrails = "## ⛔ مواضيع محظورة تماماً (خطوط حمراء):\n" + "\n".join([f"- يُمنع: {t}" for t in banned_topics])

            # ── بناء قسم السياسات الشامل ──
            rules_section = f"""
## دستور العمل (إعدادات صاحب المتجر — التزم بها حرفياً):
- **مسار الطلب:** {checkout_rule}
- **إتمام البيع:** {order_rule}
- **سياسة الخصومات:** {discount_rule}
- **استراتيجية البيع:** {upsell_rule}
- **عند عدم التوفر:** {stock_rule}
- **نقص المعلومات:** {details_rule}
- **سياسة الاسترجاع:** {refund_rule}
- **التعامل مع الشكاوى:** {complaint_rule}
- **التفاوض على السعر:** {bargain_rule}
"""
            print(f"[ENGINE] Business rules loaded: checkout={checkout_type}, upsell={upsell_type}, bargain={bargain_type}")
    except Exception as e:
        print(f"[ENGINE] Business rules error: {e}")

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
- **بيانات يجب توفرها لإتمام الطلب:** {req_text or 'لا يوجد'}
- **بيانات محظور طلبها نهائياً:** {forbidden_text or 'لا يوجد'}
- **قانون الإلزام المطلق:** لا يجوز لك إطلاقاً الانتقال لعرض الملخص أو إنشاء الفاتورة ما لم تكن قد جمعت **كل** (البيانات التي يجب توفرها).
- **الاعتماد على الذاكرة:** إذا كانت إحدى البيانات المطلوبة موجودة مسبقاً في (بيانات العميل الحالي)، قم بعرضها عليه وسؤاله "هل نعتمد نفس البيانات؟" لتأكيدها. لا تطلب منه كتابتها من الصفر. مجرد موافقته تكفي لاعتبار البيانات "تم جمعها". وإذا لم تكن موجودة، اطلبها منه نصاً.
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

    # ─── 7. FINAL SYSTEM PROMPT (3-Layer Architecture) ───────────────────────
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    from merchant.prompt_builder import build_system_prompt
    system_prompt = build_system_prompt(
        current_time=current_time,
        agent_name=agent_name,
        company_name=company_name,
        store_activity=store_activity,
        description=description,
        base_tone=base_tone,
        customer_context=customer_context,
        item_term=item_term,
        single_item_term=single_item_term,
        is_digital=is_digital,
        routing=routing,
        col_behavior_rules=col_behavior_rules,
        product_section=product_section,
        rules_section=rules_section,
        merchant_guardrails=merchant_guardrails,
        shipping_section=shipping_section,
        routing_section=routing_section,
        ai_core_strategy=ai_core_strategy,
        custom_instructions=custom_instructions,
    )



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

    # ─── 9. SMART MULTI-MODEL LLM CALL ───────────────────────────────────────
    import asyncio

    async def _call_single_model(model_info: dict, msgs: list, sys_prompt: str, temp: float, max_tok: int) -> str:
        """استدعاء نموذج واحد مع إدارة الأخطاء"""
        p = model_info["provider"]
        k = model_info["api_key"]
        m = model_info["model_id"]
        b = model_info.get("base_url", "")
        
        if   p == "openai":     return await _call_openai(k, m, msgs, temp, max_tok)
        elif p == "google":     return await _call_google(k, m, msgs, sys_prompt, temp, max_tok)
        elif p == "openrouter": return await _call_openrouter(k, m, msgs, temp, max_tok)
        elif p == "groq":       return await _call_groq(k, m, msgs, temp, max_tok)
        elif p == "anthropic":  return await _call_anthropic(k, m, msgs, sys_prompt, temp, max_tok)
        elif p == "huggingface": return await _call_huggingface(k, m, msgs, temp, max_tok)
        elif p == "cerebras":   return await _call_cerebras(k, m, msgs, temp, max_tok)
        elif p == "nvidia":     return await _call_nvidia(k, m, msgs, temp, max_tok)
        elif p == "xai":        return await _call_openai(k, m, msgs, temp, max_tok)  # xAI uses OpenAI-compatible API
        elif p == "agentrouter": return await _call_agentrouter(k, m, msgs, temp, max_tok)
        elif p == "custom":     return await _call_custom(k, m, b, msgs, temp, max_tok)
        else:                   return await _call_openrouter(k, m, msgs, temp, max_tok)

    response = None
    
    if len(resolved_models) == 1:
        # ── نموذج واحد فقط: استدعاء مباشر مع إعادة المحاولة ──
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = await _call_single_model(resolved_models[0], messages, system_prompt, ai_temperature, ai_max_tokens)
                break
            except Exception as e:
                err_msg = str(e)
                if ("429" in err_msg or "traffic" in err_msg.lower()) and attempt < max_retries:
                    print(f"[ENGINE] Rate limit hit (attempt {attempt+1}), retrying in 1.5s...")
                    await asyncio.sleep(1.5)
                    continue
                print(f"[ENGINE] Model {resolved_models[0]['name']} failed: {e}")
    else:
        # ── نماذج متعددة: التوجيه الذكي (Smart Cascade + Racing) ──
        print(f"[ENGINE] 🚀 Smart Multi-Model Router: {len(resolved_models)} models available")
        
        # المرحلة 1: تجربة النموذج الأساسي (الأعلى أولوية) مع timeout قصير
        primary = resolved_models[0]
        try:
            response = await asyncio.wait_for(
                _call_single_model(primary, messages, system_prompt, ai_temperature, ai_max_tokens),
                timeout=12.0  # 12 ثانية كحد أقصى للنموذج الأساسي
            )
            print(f"[ENGINE] ✅ Primary model '{primary['name']}' responded successfully")
        except (asyncio.TimeoutError, Exception) as primary_err:
            print(f"[ENGINE] ⚡ Primary model '{primary['name']}' failed/timeout: {primary_err}")
            
            # المرحلة 2: سباق النماذج البديلة بالتوازي
            fallback_models = resolved_models[1:]
            if fallback_models:
                print(f"[ENGINE] 🏁 Racing {len(fallback_models)} fallback models...")
                
                async def _race_model(model_info, idx):
                    """Wrapper لتتبع أي نموذج نجح"""
                    result = await _call_single_model(model_info, messages, system_prompt, ai_temperature, ai_max_tokens)
                    return (idx, model_info["name"], result)
                
                tasks = [asyncio.create_task(_race_model(m, i)) for i, m in enumerate(fallback_models)]
                
                try:
                    # انتظار أول نموذج يرد بنجاح
                    done, pending = await asyncio.wait(tasks, timeout=20.0, return_when=asyncio.FIRST_COMPLETED)
                    
                    # إلغاء المهام المتبقية لتوفير الموارد
                    for task in pending:
                        task.cancel()
                    
                    # استخراج النتيجة الأولى الناجحة
                    for task in done:
                        try:
                            idx, model_name, result = task.result()
                            if result:
                                response = result
                                print(f"[ENGINE] ✅ Fallback model '{model_name}' won the race!")
                                break
                        except Exception as task_err:
                            print(f"[ENGINE] ❌ Fallback task error: {task_err}")
                            continue
                    
                    # إذا فشلت كل المهام المكتملة، ننتظر الباقي
                    if not response and pending:
                        try:
                            done2, _ = await asyncio.wait(pending, timeout=15.0)
                            for task in done2:
                                try:
                                    idx, model_name, result = task.result()
                                    if result:
                                        response = result
                                        print(f"[ENGINE] ✅ Late fallback '{model_name}' succeeded!")
                                        break
                                except: continue
                        except: pass
                    
                except Exception as race_err:
                    print(f"[ENGINE] ❌ Race error: {race_err}")

    # ── فشل كل النماذج: رد ودي لا يرفض العميل أبداً ──
    if not response:
        response = "أهلاً بك! نعتذر عن التأخير البسيط، نظامنا يعمل على تحسين الخدمة حالياً. يرجى إعادة إرسال رسالتك بعد لحظات وسنخدمك فوراً 🙏"
        print(f"[ENGINE] ⚠️ ALL {len(resolved_models)} models failed — friendly fallback sent")

    if phone_number != "STRATEGY_GEN":
        _log_message(supabase, client_id, user_message, response, phone_number, channel, message_id)
        supabase.table("clients").update({"messages_used": messages_used + 1}).eq("id", client_id).execute()
    return response



# ─── PROVIDER IMPLEMENTATIONS ─────────────────────────────────────────────────

async def _call_openai(api_key: str, model_id: str, messages: list, temperature: float = 0.1, max_tokens: int = 600) -> str:
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        )
        data = r.json()
        if "choices" not in data:
            raise Exception(f"OpenAI error: {data.get('error', {}).get('message', str(data))}")
        return data["choices"][0]["message"]["content"].strip()

async def _call_custom(api_key: str, model_id: str, base_url: str, messages: list, temperature: float = 0.1, max_tokens: int = 600) -> str:
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            endpoint,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        )
        data = r.json()
        if r.status_code != 200 or "choices" not in data:
            raise Exception(f"Custom provider error: {data.get('error', {}).get('message', str(data))}")
        return data["choices"][0]["message"]["content"].strip()

async def _call_agentrouter(api_key: str, model_id: str, messages: list, temperature: float = 0.1, max_tokens: int = 600) -> str:
    """استدعاء نماذج عبر Agent Router (OpenAI-compatible API)"""
    async with httpx.AsyncClient(timeout=60) as c:
        try:
            r = await c.post(
                "https://agentrouter.org/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model_id, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "stream": False}
            )
            
            if r.status_code != 200:
                print(f"[AGENTROUTER ERROR] Status: {r.status_code}, Body: {r.text[:500]}")
                raise Exception(f"AgentRouter API Error ({r.status_code}): {r.text[:200]}")
            
            data = r.json()
            if "choices" not in data:
                raise Exception(f"AgentRouter error: unexpected response: {str(data)[:300]}")
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"[AGENTROUTER EXCEPTION] {str(e)[:500]}")
            raise


async def _call_openrouter(api_key: str, model_id: str, messages: list, temperature: float = 0.1, max_tokens: int = 600) -> str:
    async with httpx.AsyncClient(timeout=25) as c:
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
    async with httpx.AsyncClient(timeout=20) as c:
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