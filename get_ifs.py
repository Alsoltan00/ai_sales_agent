with open('templates/merchant_base.html', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if '{%' in line and ('if ' in line or 'elif' in line or 'else' in line or 'endif' in line):
            print(f"{i+1}: {line.strip()}")
