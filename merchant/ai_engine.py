import os
import json
import httpx
from database.db_client import get_supabase_client


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

    # ─── 2. AI MODEL RESOLUTION (Plan → Config) ──────────────────────────────
    api_key, model_id, provider = None, "gpt-3.5-turbo", "openai"
    try:
        # Check plan-assigned model first
        plan_name = c.get("subscription_plan")
        if plan_name:
            p_det = supabase.table("subscription_plans").select("permissions").eq("name", plan_name).single().execute()
            if p_det.data:
                perms = p_det.data.get("permissions", {})
                if isinstance(perms, str):
                    perms = json.loads(perms)
                mid = perms.get("assigned_model_id")
                if mid:
                    gm = supabase.table("global_ai_models").select("*").eq("id", mid).single().execute()
                    if gm.data:
                        api_key  = gm.data["api_key"]
                        model_id = gm.data["model_id"]
                        provider = gm.data["provider"].lower()
                        print(f"[ENGINE] Model from PLAN: {model_id} via {provider}")

        # Fallback: merchant's own active config
        if not api_key:
            m_cfg = supabase.table("ai_models_config").select("*").eq("client_id", client_id).eq("is_active", True).execute()
            if m_cfg.data:
                api_key  = m_cfg.data[0]["api_key"]
                model_id = m_cfg.data[0]["model_id"]
                provider = m_cfg.data[0]["provider"].lower()
                print(f"[ENGINE] Model from CONFIG: {model_id} via {provider}")

        if not api_key:
            print(f"[ENGINE] ERROR: No API key found for client {client_id}")

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
            print(f"[ENGINE] No history for {search_phone}")
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
                    order_rule = f"بعد أن يطلب العميل {single_item_term}، اسأله أولاً: 'هل ترغب بإضافة شيء آخر؟'. بعد تأكيده على الاكتفاء، انتقل فوراً لتنفيذ (بروتوكول إتمام الطلب) المذكور في القواعد لتأكيد العنوان وعرض الملخص."
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

    # ─── 6.5 SHIPPING DATA ─────────────────────────────────────────────────────
    shipping_section = ""
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
                    
                    line = f"  - {z['zone_name']}: {price} ريال"
                    if price == 0:
                        line = f"  - {z['zone_name']}: مجاني"
                    if free_enabled and free_min > 0:
                        line += f" (شحن مجاني عند تجاوز الطلب {free_min} ريال)"
                    zones_list.append(line)
                zones_text = "\n".join(zones_list)

            shipping_section = f"""
## سياسة الشحن (التزم بها حرفياً):
- مناطق الشحن المتاحة وأسعارها:
{zones_text}
- **إذا ذكر العميل مدينة أو منطقة غير موجودة في القائمة أعلاه:** {unavail_msg if unavail_msg else 'أخبره بلطف أن الشحن غير متاح حالياً لمنطقته وسيتم تحويل طلبه للإدارة.'}
- عند حساب الفاتورة النهائية، أضف سعر الشحن بناءً على مدينة العميل وأظهره كبند منفصل في الملخص. إذا كان الشحن مجاني (بسبب تجاوز الحد الأدنى) اذكر ذلك.
- أضف حقل "shipping_cost" في ORDER_DATA بالقيمة الصحيحة.
"""
            print(f"[ENGINE] Shipping zones loaded: {len(ship_zones)} zones")
    except Exception as e:
        print(f"[ENGINE] Shipping data error: {e}")

    # ─── 7. FINAL SYSTEM PROMPT ───────────────────────────────────────────────
    phone_instruction = "لا تطلب رقم الجوال أبداً، لأننا نتحدث معه عبر الواتساب ورقم هاتفه معروف لدينا مسبقاً." if channel.startswith("whatsapp") else "اطلب رقم الجوال للتواصل ضمن البيانات المطلوبة."

    system_prompt = f"""أنت "{agent_name}"، موظف مبيعات في "{company_name}".
نشاط المتجر: {store_activity}.
{f'نبذة: {description}' if description else ''}
نبرة الصوت: {base_tone}.

## قواعد الحوار (صارمة):
1. تحدث كإنسان طبيعي ودود. لا تذكر مصطلحات تقنية.
2. لا تكرر التعريف بنفسك إذا وُجدت رسائل سابقة.
3. لا تطلب بيانات العميل الشخصية إلا عند تأكيد الطلب النهائي. لكن إذا أخبرك العميل اسمه أو أي معلومة عن نفسه **بشكل تطوعي**، استخدمها بود ولا تقل أبداً "لا أستطيع تذكر الأسماء" أو ما يشابهها.
4. **فهم السياق الاجتماعي والذاكرة (مهم جداً):**
   - **أسئلة الذاكرة:** إذا سألك العميل عن اسمه (مثل "ما اسمي؟" أو "هل تتذكرني؟"):
     * إذا كان قد ذكر اسمه في الرسائل السابقة، أخبره باسمه بكل ود ومزاح خفيف. مثال: "أكيد أعرفك يا أصيل! معقولة أنسى؟ 😄"
     * إذا كانت المحادثة جديدة ولم يذكر اسمه بعد، اعتذر بلطف شديد واطلب منه أن يتشرف بذكر اسمه. مثال: "للأسف لسه ما تشرفنا بمعرفة اسمك الكريم، وش اسمك؟ 🌟"
   - إذا أخبرك العميل اسمه → نادِه باسمه مباشرة بود. مثال: "أهلاً أصيل! تشرفنا 🌟"
   - إذا أخبرك بأصله أو مكان سكنه → تفاعل بحماس ولا تذكر الشحن. مثال: "يا مرحبا! أهلاً وسهلاً فيك 🌟 كيف أقدر أساعدك اليوم؟"
   - **مكان السكن الحالي** هو المعيار للشحن (وليس البلد الأصلي). إذا قال "من اليمن وأسكن في السعودية" فهو عميل سعودي يمكن الشحن له.
   - **لا تقفز مباشرة لموضوع الشحن أو القيود** إلا إذا سأل العميل عن الشحن تحديداً أو عند إتمام الطلب.
5. **حساب الإجمالي:** عند حساب إجمالي الطلب، ابحث عن الحقول التي تدل على السعر (مثل: السعر، التكلفة، السعر الحالي، Price، Cost) وقم بضرب السعر في الكمية المطلوبة بدقة رياضية. تجاهل أي رموز عملة (مثل ريال، SR) عند الحساب.
6. **بروتوكول إتمام الطلب (إلزامي وصارم):**
   - **الخطوة 1 (جمع البيانات وعرض الملخص):** عندما يقرر العميل الشراء، **يجب** أولاً التأكد من توفر البيانات التالية (الاسم، العنوان، طريقة الدفع المفضلة، ورقم الجوال إذا لم تكن في الواتساب).
     * **إذا كانت أي معلومة ناقصة (مثل الاسم أو العنوان):** اطلبها من العميل بلطف أولاً ولا تعرض الملخص النهائي.
     * **إذا توفرت كل البيانات:** أرسل له رسالة واحدة تحتوي على:
       1. قائمة المنتجات والإجمالي مع الشحن.
       2. اسم العميل.
       3. عنوان التوصيل.
       4. {phone_instruction}
       5. طريقة الدفع التي اختارها (اخبره بالخيارات المتاحة في دستور العمل إذا لم يختر بعد).
       6. ثم اسأله: "هل هذه البيانات صحيحة وتوافق على إتمام الطلب؟" (مع أزرار التأكيد).
   - **الخطوة 2 (التأكيد النهائي وإرسال الكود السري):** **فقط بعد أن يضغط العميل على زر الموافقة رداً على الملخص المكتمل**، أضف هذا الوسم المخفي في نهاية ردك تماماً: `[ORDER_DATA: {{"customer_name": "اسم العميل", "customer_phone": "رقم الجوال", "customer_address": "العنوان الفعلي", "items": [{{"name": "اسم المنتج", "qty": 1, "price": 100}}], "total_amount": 100, "payment_method": "طريقة الدفع", "order_type": "purchase"}}]`. يجب أن تكون جميع البيانات ممتلئة وليست فارغة أو "..."، لأنك سألت عنها مسبقاً. تأكد أن الـ JSON صحيح تقنياً. لا ترسل هذا الوسم أبداً قبل موافقة العميل على الملخص.
## ⛔ قانون عرض {item_term} (أهم قانون — كسره يُعتبر خطأ فادح):
**يُمنع منعاً باتاً ذكر أكثر من 3 عناصر في رد واحد مهما كان السبب.**
عندما يسأل العميل سؤالاً عاماً مثل: "ماذا لديك؟" أو "أعطني خيارات" أو "ايش عندكم؟" أو أي صيغة مشابهة:
1. **لا تسرد {item_term} أبداً.** بدلاً من ذلك، حدد الفئات/الأقسام الرئيسية من القائمة وأذكرها فقط كعناوين.
2. اسأل العميل أي فئة يهتم بها.
3. مثال صحيح: "أهلاً بك! 🌟 لدينا عدة أقسام: شامبو، بلسم، صبغات شعر، ومنتجات عناية بالبشرة. أي قسم يهمك؟"
4. مثال خاطئ: سرد أسماء المنتجات أو تفاصيلها مباشرة.

## بروتوكول التعامل مع الطلبات (إلزامي):
عندما يحدد العميل فئة معينة وفي القائمة أكثر من خيار:

**الخطوة 1 — أذكر الخيارات الرئيسية فقط (بدون تفاصيل أو أسعار):**
حدد أقصى 3 خيارات مختلفة واسأل العميل أيهما يفضل.
مثال: "لدينا شامبو جارنير وشامبو لوريال. أيهما يناسبك؟"

**الخطوة 2 — بعد أن يختار، اعرض التفاصيل:**
أذكر الأحجام أو الأنواع المتوفرة ضمن اختياره.
مثال: "شامبو جارنير متوفر بحجم 200 مل و400 مل. أيهما تفضل؟"

**الخطوة 3 — المنتج النهائي:**
أعطه تفاصيل المنتج الذي اختاره (الاسم + السعر).

## خطوات الفحص الإلزامية قبل تأكيد توفر أي شيء للعميل:
1. ابحث في (قائمة البيانات المتوفرة) عن طلب العميل.
2. إذا وجدت {single_item_term}، **يجب عليك أولاً مراجعة (تعليمات حقول البيانات) وتطبيقها حرفياً على هذا {single_item_term} تحديداً.**
3. إذا كانت التعليمات تطلب منك اعتباره "غير متوفر" بسبب قيمة معينة (مثل الكمية 0، أو محجوز)، فيجب عليك إخفاءه تماماً والرد كأنه غير موجود في القائمة أبداً، وتطبيق (قواعد تصنيف الأسئلة - الحالة 2).

{col_behavior_rules}

## قائمة البيانات المتوفرة ({item_term} - المصدر الوحيد للحقيقة):
{product_section}

{rules_section}

{shipping_section}

## قانون منع الهلوسة (غير قابل للكسر):
- **لا تكرر أي {single_item_term} أكثر من مرة واحدة في نفس الرد أبداً.** إذا ظهر نفس العنصر مكرراً في القائمة، اذكره مرة واحدة فقط.
- لا تذكر أي {single_item_term} غير موجود في القائمة أعلاه أبداً. إذا سأل العميل عن شيء غير موجود، التزم فوراً بـ (قواعد تصنيف الأسئلة) أدناه لتحديد كيفية الرد.
- لا تذكر أي اسم تجاري أو ماركة إلا إذا كانت مكتوبة صراحةً في القائمة.
- المرجعيات الترتيبية: إذا قال العميل "الأول"، "الثاني"، "الأخير"، احسب الترتيب حرفياً بناءً على ما ذكرته أنت في آخر رسالة دون تجاهل أي شيء.
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
- عرض فئات: "لدينا شامبو وبلسم وصبغات" → [BUTTONS: شامبو | بلسم | صبغات]
- سؤال تأكيد: "هل تريد إضافة شيء آخر؟" → [BUTTONS: نعم ✅ | لا ❌]
- عرض خيارين: "جارنير أو لوريال؟" → [BUTTONS: جارنير | لوريال]
- موافقة على الطلب: "هل البيانات صحيحة؟" → [BUTTONS: نعم، أوافق ✅ | تعديل ✏️]
"""

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

    # ─── 9. LLM CALL ──────────────────────────────────────────────────────────
    try:
        if not api_key:
            raise ValueError(f"No API key for provider '{provider}'. Check ai_models_config.")

        if   provider == "openai":     response = await _call_openai(api_key, model_id, messages)
        elif provider == "google":     response = await _call_google(api_key, model_id, messages, system_prompt)
        elif provider == "openrouter": response = await _call_openrouter(api_key, model_id, messages)
        elif provider == "groq":       response = await _call_groq(api_key, model_id, messages)
        elif provider == "anthropic":  response = await _call_anthropic(api_key, model_id, messages, system_prompt)
        elif provider == "huggingface": response = await _call_huggingface(api_key, model_id, messages)
        elif provider == "cerebras":    response = await _call_cerebras(api_key, model_id, messages)
        else:
            print(f"[ENGINE] Unknown provider '{provider}', falling back to openrouter")
            response = await _call_openrouter(api_key, model_id, messages)

        _log_message(supabase, client_id, user_message, response, phone_number, channel, message_id)
        supabase.table("clients").update({"messages_used": messages_used + 1}).eq("id", client_id).execute()
        print(f"[ENGINE] Response OK ({len(response)} chars)")
        return response

    except Exception as e:
        print(f"[ENGINE] CRITICAL LLM ERROR [{provider}]: {e}")
        return f"عذراً، واجهت مشكلة تقنية. يرجى التواصل مع المتجر مباشرة."


# ─── PROVIDER IMPLEMENTATIONS ─────────────────────────────────────────────────

async def _call_openai(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model_id, "messages": messages, "temperature": 0.1, "max_tokens": 600}
        )
        data = r.json()
        if "choices" not in data:
            raise Exception(f"OpenAI error: {data.get('error', {}).get('message', str(data))}")
        return data["choices"][0]["message"]["content"].strip()


async def _call_openrouter(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model_id, "messages": messages, "temperature": 0.1, "max_tokens": 600}
        )
        data = r.json()
        if "choices" not in data:
            raise Exception(f"OpenRouter error: {data.get('error', {}).get('message', str(data))}")
        return data["choices"][0]["message"]["content"].strip()


async def _call_groq(api_key: str, model_id: str, messages: list) -> str:
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": model_id, "messages": messages, "temperature": 0.1, "max_tokens": 600}
        )
        data = r.json()
        if "choices" not in data:
            raise Exception(f"Groq error: {data.get('error', {}).get('message', str(data))}")
        return data["choices"][0]["message"]["content"].strip()


async def _call_cerebras(api_key: str, model_id: str, messages: list) -> str:
    """استدعاء نماذج Cerebras السريعة جداً"""
    async with httpx.AsyncClient(timeout=45) as c:
        try:
            r = await c.post(
                "https://api.cerebras.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model_id, "messages": messages, "temperature": 0.1, "max_tokens": 600}
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

async def _call_huggingface(api_key: str, model_id: str, messages: list) -> str:
    """استدعاء نماذج Hugging Face عبر Inference API"""
    async with httpx.AsyncClient(timeout=60) as c:
        try:
            r = await c.post(
                "https://api-inference.huggingface.co/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model_id, "messages": messages, "temperature": 0.1, "max_tokens": 600}
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

async def _call_anthropic(api_key: str, model_id: str, messages: list, system: str) -> str:
    user_msgs = [m for m in messages if m["role"] != "system"]
    async with httpx.AsyncClient(timeout=45) as c:
        r = await c.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            json={"model": model_id, "system": system, "messages": user_msgs, "max_tokens": 600}
        )
        data = r.json()
        if "content" not in data:
            raise Exception(f"Anthropic error: {data.get('error', {}).get('message', str(data))}")
        return data["content"][0]["text"].strip()


async def _call_google(api_key: str, model_id: str, messages: list, system: str) -> str:
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
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 600}
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