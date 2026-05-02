const activitiesCatalog = [
    // التجزئة والتسوق
    { id: 'ret_1', domain: 'التجزئة والتسوق', name: 'سوبر ماركت', description: 'مواد غذائية.', icon: 'ti-shopping-cart', tags: ['بقالة', 'أكل'], rating: 4.8, cost: '$$$' },
    { id: 'ret_2', domain: 'التجزئة والتسوق', name: 'عطور وبخور', description: 'عطور وبخور.', icon: 'ti-perfume', tags: ['عطر', 'عود'], rating: 4.9, cost: '$$' },
    { id: 'ret_3', domain: 'التجزئة والتسوق', name: 'إكسسوارات', description: 'حلي ومجوهرات.', icon: 'ti-diamond', tags: ['ذهب', 'فضة'], rating: 4.7, cost: '$$$$' },
    { id: 'ret_4', domain: 'التجزئة والتسوق', name: 'مستحضرات تجميل', description: 'أدوات تجميل.', icon: 'ti-brush', tags: ['مكياج'], rating: 4.6, cost: '$$' },
    { id: 'ret_5', domain: 'التجزئة والتسوق', name: 'ملابس نسائية', description: 'أزياء نسائية.', icon: 'ti-hanger', tags: ['أزياء', 'فساتين'], rating: 4.5, cost: '$$' },
    { id: 'ret_6', domain: 'التجزئة والتسوق', name: 'ملابس رجالية', description: 'أزياء رجالية.', icon: 'ti-shirt', tags: ['ثياب', 'قمصان'], rating: 4.7, cost: '$$' },
    { id: 'ret_7', domain: 'التجزئة والتسوق', name: 'أحذية وحقائب', description: 'حقائب وأحذية.', icon: 'ti-shoe', tags: ['جزم', 'شنط'], rating: 4.6, cost: '$$' },
    { id: 'ret_8', domain: 'التجزئة والتسوق', name: 'عبايات وطرح', description: 'عبايات خليجية.', icon: 'ti-shopping-bag', tags: ['عباية', 'طرحة'], rating: 4.9, cost: '$$$' },
    { id: 'ret_9', domain: 'التجزئة والتسوق', name: 'ألعاب أطفال', description: 'ألعاب متنوعة.', icon: 'ti-puzzle', tags: ['ألعاب', 'اطفال'], rating: 4.8, cost: '$$' },
    { id: 'ret_10', domain: 'التجزئة والتسوق', name: 'قرطاسية ومكتبة', description: 'أدوات مدرسية.', icon: 'ti-book', tags: ['دفاتر', 'أقلام'], rating: 4.5, cost: '$' },
    { id: 'ret_11', domain: 'التجزئة والتسوق', name: 'زهور وتغليف هدايا', description: 'هدايا وزهور.', icon: 'ti-flower', tags: ['ورد', 'هدايا'], rating: 4.8, cost: '$$' },
    { id: 'ret_12', domain: 'التجزئة والتسوق', name: 'أجهزة منزلية', description: 'أجهزة مطبخ.', icon: 'ti-device-tv', tags: ['ثلاجة', 'فرن'], rating: 4.7, cost: '$$$$' },
    { id: 'ret_13', domain: 'التجزئة والتسوق', name: 'أثاث منزلي', description: 'غرف ومجالس.', icon: 'ti-sofa', tags: ['كنب', 'سرير'], rating: 4.6, cost: '$$$$' },
    
    // المطاعم والضيافة
    { id: 'food_1', domain: 'المطاعم والضيافة', name: 'مقهى مختص', description: 'قهوة ومشروبات.', icon: 'ti-coffee', tags: ['كوفي', 'قهوة'], rating: 4.9, cost: '$$' },
    { id: 'food_2', domain: 'المطاعم والضيافة', name: 'وجبات سريعة', description: 'برجر وبطاطس.', icon: 'ti-meat', tags: ['فاست فود'], rating: 4.5, cost: '$' },
    { id: 'food_3', domain: 'المطاعم والضيافة', name: 'مطعم شعبي', description: 'أكلات محلية.', icon: 'ti-soup', tags: ['مندي', 'كبسة'], rating: 4.7, cost: '$$' },
    { id: 'food_4', domain: 'المطاعم والضيافة', name: 'مطعم مشويات', description: 'كباب وأوصال.', icon: 'ti-flame', tags: ['لحم', 'شوي'], rating: 4.6, cost: '$$$' },
    { id: 'food_5', domain: 'المطاعم والضيافة', name: 'مخبز وحلويات', description: 'معجنات وكيك.', icon: 'ti-cookie', tags: ['حلى', 'مخبوزات'], rating: 4.8, cost: '$$' },
    { id: 'food_6', domain: 'المطاعم والضيافة', name: 'عصائر طازجة', description: 'عصائر وفواكه.', icon: 'ti-cup', tags: ['عصير', 'طازج'], rating: 4.7, cost: '$' },
    { id: 'food_7', domain: 'المطاعم والضيافة', name: 'مطعم بحري', description: 'أسماك ومأكولات.', icon: 'ti-fish', tags: ['سمك', 'روبيان'], rating: 4.8, cost: '$$$$' },
    { id: 'food_8', domain: 'المطاعم والضيافة', name: 'بيتزا ومعجنات', description: 'بيتزا إيطالية.', icon: 'ti-pizza', tags: ['بيتزا', 'فطائر'], rating: 4.6, cost: '$$' },
    { id: 'food_9', domain: 'المطاعم والضيافة', name: 'مطعم شاورما', description: 'شاورما وفلافل.', icon: 'ti-sausage', tags: ['دجاج', 'لحم'], rating: 4.7, cost: '$' },

    // التعليم والتدريب
    { id: 'edu_1', domain: 'التعليم والتدريب', name: 'مركز لغات', description: 'تدريب لغات.', icon: 'ti-language', tags: ['انجليزي'], rating: 4.8, cost: '$$$' },
    { id: 'edu_2', domain: 'التعليم والتدريب', name: 'دروس تقوية', description: 'دروس خصوصية.', icon: 'ti-book-2', tags: ['مدرسة'], rating: 4.6, cost: '$$' },
    { id: 'edu_3', domain: 'التعليم والتدريب', name: 'تدريب مهني', description: 'دورات تطوير.', icon: 'ti-code', tags: ['برمجة'], rating: 4.9, cost: '$$$' },
    { id: 'edu_4', domain: 'التعليم والتدريب', name: 'استشارات تعليمية', description: 'توجيه طلابي.', icon: 'ti-compass', tags: ['جامعة', 'قبول'], rating: 4.7, cost: '$$' },
    { id: 'edu_5', domain: 'التعليم والتدريب', name: 'تعليم قيادة', description: 'مدرسة قيادة.', icon: 'ti-steering-wheel', tags: ['سيارة', 'رخصة'], rating: 4.5, cost: '$$$' },

    // الصحة والرياضة
    { id: 'health_1', domain: 'الصحة والرياضة', name: 'صيدلية', description: 'أدوية طبية.', icon: 'ti-prescription', tags: ['علاج'], rating: 4.8, cost: '$$' },
    { id: 'health_2', domain: 'الصحة والرياضة', name: 'نادي رياضي', description: 'صالة رياضية.', icon: 'ti-barbell', tags: ['جيم', 'لياقة'], rating: 4.7, cost: '$$$' },
    { id: 'health_3', domain: 'الصحة والرياضة', name: 'عيادة أسنان', description: 'طب أسنان.', icon: 'ti-dental', tags: ['طبيب'], rating: 4.9, cost: '$$$$' },
    { id: 'health_4', domain: 'الصحة والرياضة', name: 'مركز علاج طبيعي', description: 'علاج وتأهيل.', icon: 'ti-stretching', tags: ['مساج', 'تأهيل'], rating: 4.8, cost: '$$$' },
    { id: 'health_5', domain: 'الصحة والرياضة', name: 'مكملات غذائية', description: 'فيتامينات.', icon: 'ti-pill', tags: ['بروتين'], rating: 4.7, cost: '$$' },
    { id: 'health_6', domain: 'الصحة والرياضة', name: 'معدات طبية', description: 'أجهزة طبية.', icon: 'ti-stethoscope', tags: ['مستلزمات'], rating: 4.6, cost: '$$$$' },

    // التكنولوجيا والأعمال
    { id: 'tech_1', domain: 'التكنولوجيا والأعمال', name: 'تطوير برمجيات', description: 'برمجة نظم.', icon: 'ti-device-laptop', tags: ['موقع'], rating: 4.9, cost: '$$$$' },
    { id: 'tech_2', domain: 'التكنولوجيا والأعمال', name: 'تسويق رقمي', description: 'حملات إعلانية.', icon: 'ti-ad', tags: ['اعلانات'], rating: 4.8, cost: '$$$' },
    { id: 'tech_3', domain: 'التكنولوجيا والأعمال', name: 'استشارات أعمال', description: 'دراسات جدوى.', icon: 'ti-chart-bar', tags: ['دراسة'], rating: 4.7, cost: '$$$$' },
    { id: 'tech_4', domain: 'التكنولوجيا والأعمال', name: 'صيانة جوالات', description: 'إصلاح هواتف.', icon: 'ti-device-mobile', tags: ['شاشة', 'بطارية'], rating: 4.6, cost: '$$' },
    { id: 'tech_5', domain: 'التكنولوجيا والأعمال', name: 'بيع إلكترونيات', description: 'حواسيب وأجهزة.', icon: 'ti-cpu', tags: ['لابتوب', 'تقنية'], rating: 4.8, cost: '$$$$' },
    { id: 'tech_6', domain: 'التكنولوجيا والأعمال', name: 'استضافة وسيرفرات', description: 'خدمات ويب.', icon: 'ti-server', tags: ['دومين', 'كلاود'], rating: 4.9, cost: '$$$' },

    // السياحة والترفيه
    { id: 'tour_1', domain: 'السياحة والترفيه', name: 'سفر وسياحة', description: 'تذاكر وفنادق.', icon: 'ti-plane-tilt', tags: ['طيران'], rating: 4.6, cost: '$$$' },
    { id: 'tour_2', domain: 'السياحة والترفيه', name: 'تنظيم فعاليات', description: 'مؤتمرات ومعارض.', icon: 'ti-confetti', tags: ['حفلة'], rating: 4.8, cost: '$$$$' },
    { id: 'tour_3', domain: 'السياحة والترفيه', name: 'ملاهي وألعاب', description: 'مدينة ترفيهية.', icon: 'ti-ticket', tags: ['لعب', 'عائلة'], rating: 4.7, cost: '$$' },
    { id: 'tour_4', domain: 'السياحة والترفيه', name: 'شقق فندقية', description: 'إسكان مفروش.', icon: 'ti-building', tags: ['ايجار', 'سكن'], rating: 4.5, cost: '$$$' },
    { id: 'tour_5', domain: 'السياحة والترفيه', name: 'تأجير سيارات', description: 'تأجير يومي.', icon: 'ti-car', tags: ['ايجار', 'مركبة'], rating: 4.6, cost: '$$$' },

    // الخدمات العامة والمهن
    { id: 'serv_1', domain: 'الخدمات العامة', name: 'صالون حلاقة', description: 'حلاقة رجالية.', icon: 'ti-cut', tags: ['شعر', 'دقن'], rating: 4.7, cost: '$' },
    { id: 'serv_2', domain: 'الخدمات العامة', name: 'مشغل نسائي', description: 'تجميل نسائي.', icon: 'ti-scissors', tags: ['شعر', 'مكياج'], rating: 4.8, cost: '$$' },
    { id: 'serv_3', domain: 'الخدمات العامة', name: 'مغسلة ملابس', description: 'غسيل وكوي.', icon: 'ti-wash-machine', tags: ['تنظيف', 'ملابس'], rating: 4.5, cost: '$' },
    { id: 'serv_4', domain: 'الخدمات العامة', name: 'تنظيف مباني', description: 'نظافة عامة.', icon: 'ti-broom', tags: ['سجاد', 'منازل'], rating: 4.6, cost: '$$' },
    { id: 'serv_5', domain: 'الخدمات العامة', name: 'مكتب محاماة', description: 'استشارات قانونية.', icon: 'ti-scale', tags: ['قانون', 'محكمة'], rating: 4.9, cost: '$$$$' },
    { id: 'serv_6', domain: 'الخدمات العامة', name: 'مكتب عقار', description: 'بيع وتأجير.', icon: 'ti-home', tags: ['أراضي', 'فلل'], rating: 4.7, cost: '$$$$' },
    { id: 'serv_7', domain: 'الخدمات العامة', name: 'خياطة رجالية', description: 'تفصيل ثياب.', icon: 'ti-needle', tags: ['خياط', 'قماش'], rating: 4.8, cost: '$$' },
    { id: 'serv_8', domain: 'الخدمات العامة', name: 'صيانة سيارات', description: 'ورشة ميكانيكا.', icon: 'ti-tool', tags: ['زيت', 'سمكرة'], rating: 4.6, cost: '$$$' }
];

// دالة البحث الذكي
function searchActivities(query) {
    if (!query) return activitiesCatalog;
    
    query = query.toLowerCase().trim();
    
    return activitiesCatalog.map(activity => {
        let score = 0;
        const name = activity.name.toLowerCase();
        const desc = activity.description.toLowerCase();
        const domain = activity.domain.toLowerCase();
        
        // 1. تطابق تام
        if (name === query) score += 100;
        
        // 2. يبدأ بـ
        else if (name.startsWith(query)) score += 50;
        
        // 3. يحتوي على
        else if (name.includes(query)) score += 30;
        
        // 4. تطابق في الكلمات المفتاحية (Tags)
        if (activity.tags.some(tag => tag.toLowerCase().includes(query))) score += 20;
        
        // 5. تطابق في المجال
        if (domain.includes(query)) score += 10;
        
        // 6. تطابق في الوصف
        if (desc.includes(query)) score += 5;
        
        return { ...activity, score };
    })
    .filter(a => a.score > 0)
    .sort((a, b) => b.score - a.score);
}
