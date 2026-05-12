import re

with open('templates/merchant_base.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

stack = []
for i, line in enumerate(lines):
    line_num = i + 1
    # Match block tags
    matches = re.finditer(r'\{%\s*(if|elif|else|endif|for|endfor)\b[^%]*%\}', line)
    for m in matches:
        tag = m.group(1)
        if tag == 'if' or tag == 'for':
            stack.append((tag, line_num))
            print(f"L{line_num}: {m.group(0)} -> Depth: {len(stack)}")
        elif tag == 'endif' or tag == 'endfor':
            if stack:
                stack.pop()
                print(f"L{line_num}: {m.group(0)} -> Depth: {len(stack)}")
            else:
                print(f"L{line_num}: ERROR! {m.group(0)} WITHOUT OPENING TAG")
        else:
            print(f"L{line_num}: {m.group(0)} -> Depth: {len(stack)}")

if stack:
    print(f"ERROR: Unclosed tags: {stack}")
else:
    print("All tags matched perfectly!")
