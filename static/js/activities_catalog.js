const activitiesCatalog = [
    // التجزئة والتسوق
    { id: 'ret_1', domain: 'التجزئة والتسوق', name: 'سوبر ماركت', description: 'بيع المواد الغذائية والاستهلاكية اليومية.', icon: 'ti-shopping-cart', tags: ['بقالة', 'أكل', 'شرب'], rating: 4.8, cost: '$$$' },
    { id: 'ret_2', domain: 'التجزئة والتسوق', name: 'عطور وبخور', description: 'بيع العطور الشرقية والفرنسية والبخور بأنواعه.', icon: 'ti-perfume', tags: ['عطر', 'عود', 'تجميل'], rating: 4.9, cost: '$$' },
    { id: 'ret_3', domain: 'التجزئة والتسوق', name: 'إكسسوارات ومجوهرات', description: 'بيع الحلي والمجوهرات الثمينة والإكسسوارات.', icon: 'ti-diamond', tags: ['ذهب', 'فضة', 'زينة'], rating: 4.7, cost: '$$$$' },
    { id: 'ret_4', domain: 'التجزئة والتسوق', name: 'مستحضرات تجميل', description: 'بيع أدوات ومستحضرات التجميل والعناية بالبشرة.', icon: 'ti-brush', tags: ['مكياج', 'عناية', 'بشرة'], rating: 4.6, cost: '$$' },
    
    // المطاعم والضيافة
    { id: 'food_1', domain: 'المطاعم والضيافة', name: 'مقهى مختص', description: 'تقديم القهوة المختصة والمشروبات الساخنة والباردة.', icon: 'ti-coffee', tags: ['كوفي', 'قهوة', 'مشروبات'], rating: 4.9, cost: '$$' },
    { id: 'food_2', domain: 'المطاعم والضيافة', name: 'مطعم وجبات سريعة', description: 'تقديم البرجر والبطاطس والوجبات السريعة التحضير.', icon: 'ti-burger', tags: ['فاست فود', 'برجر', 'أكل'], rating: 4.5, cost: '$' },
    { id: 'food_3', domain: 'المطاعم والضيافة', name: 'مطعم شعبي', description: 'تقديم المأكولات الشعبية والمحلية التقليدية.', icon: 'ti-soup', tags: ['كبسة', 'مندي', 'تراث'], rating: 4.7, cost: '$$' },

    // التعليم والتدريب
    { id: 'edu_1', domain: 'التعليم والتدريب', name: 'مركز لغات', description: 'تدريب وتعليم اللغات الأجنبية (إنجليزية، فرنسية...).', icon: 'ti-language', tags: ['لغة', 'انجليزي', 'توفل'], rating: 4.8, cost: '$$$' },
    { id: 'edu_2', domain: 'التعليم والتدريب', name: 'دروس تقوية', description: 'تقديم دروس خصوصية للطلاب في مختلف المراحل.', icon: 'ti-book', tags: ['مدرسة', 'طالب', 'مدرس'], rating: 4.6, cost: '$$' },
    { id: 'edu_3', domain: 'التعليم والتدريب', name: 'تدريب مهني وتقني', description: 'دورات في البرمجة، التصميم، وإدارة الأعمال.', icon: 'ti-code', tags: ['برمجة', 'حاسب', 'دورة'], rating: 4.9, cost: '$$$' },

    // الصحة والرياضة
    { id: 'health_1', domain: 'الصحة والرياضة', name: 'صيدلية', description: 'بيع الأدوية والمستلزمات الطبية والعناية الشخصية.', icon: 'ti-prescription', tags: ['دواء', 'علاج', 'طبي'], rating: 4.8, cost: '$$' },
    { id: 'health_2', domain: 'الصحة والرياضة', name: 'نادي رياضي', description: 'صالة رياضية مجهزة بأحدث الأجهزة ومدربين شخصيين.', icon: 'ti-barbell', tags: ['جيم', 'لياقة', 'حديد'], rating: 4.7, cost: '$$$' },
    { id: 'health_3', domain: 'الصحة والرياضة', name: 'عيادة أسنان', description: 'خدمات طب وتجميل الأسنان.', icon: 'ti-dental', tags: ['طبيب', 'أسنان', 'تقويم'], rating: 4.9, cost: '$$$$' },

    // التكنولوجيا والأعمال
    { id: 'tech_1', domain: 'التكنولوجيا والأعمال', name: 'تطوير برمجيات', description: 'برمجة المواقع والتطبيقات والأنظمة المخصصة.', icon: 'ti-device-laptop', tags: ['موقع', 'تطبيق', 'تقنية'], rating: 4.9, cost: '$$$$' },
    { id: 'tech_2', domain: 'التكنولوجيا والأعمال', name: 'تسويق رقمي', description: 'إدارة الحملات الإعلانية وحسابات التواصل الاجتماعي.', icon: 'ti-ad', tags: ['اعلانات', 'سوشيال', 'ماركتنج'], rating: 4.8, cost: '$$$' },
    { id: 'tech_3', domain: 'التكنولوجيا والأعمال', name: 'استشارات أعمال', description: 'تقديم دراسات جدوى واستشارات إدارية ومالية.', icon: 'ti-chart-bar', tags: ['دراسة', 'جدوى', 'استشارة'], rating: 4.7, cost: '$$$$' },

    // السياحة والترفيه
    { id: 'tour_1', domain: 'السياحة والترفيه', name: 'وكالة سفر وسياحة', description: 'حجوزات تذاكر طيران وفنادق وبرامج سياحية.', icon: 'ti-plane-tilt', tags: ['سفر', 'طيران', 'فندق'], rating: 4.6, cost: '$$$' },
    { id: 'tour_2', domain: 'السياحة والترفيه', name: 'تنظيم فعاليات', description: 'تنظيم وتجهيز المؤتمرات والحفلات والمعارض.', icon: 'ti-confetti', tags: ['حفلة', 'معرض', 'ايفنت'], rating: 4.8, cost: '$$$$' },
    { id: 'tour_3', domain: 'السياحة والترفيه', name: 'ملاهي وألعاب', description: 'مدينة ألعاب ترفيهية للأطفال والعائلات.', icon: 'ti-ticket', tags: ['لعب', 'عائلة', 'تسلية'], rating: 4.7, cost: '$$' }
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
