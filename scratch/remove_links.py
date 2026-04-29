import os, glob, re

pattern = re.compile(r'\s*<a href="/merchant/ai-training"[^>]*>.*?تدريب الذكاء الاصطناعي.*?</a>', re.DOTALL | re.IGNORECASE)

files = glob.glob('templates/merchant/*.html') + glob.glob('templates/merchant_home.html')

for f in files:
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    new_content = pattern.sub('', content)
    if new_content != content:
        with open(f, 'w', encoding='utf-8') as file:
            file.write(new_content)
        print(f'Removed from {f}')
