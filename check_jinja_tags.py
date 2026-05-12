import re

with open('templates/merchant_base.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

out = open('check_jinja_out.txt', 'w', encoding='utf-8')
stack = []
for i, line in enumerate(lines):
    line_num = i + 1
    # Match block tags
    matches = re.finditer(r'\{%\s*(if|elif|else|endif|for|endfor)\b[^%]*%\}', line)
    for m in matches:
        tag = m.group(1)
        if tag == 'if' or tag == 'for':
            stack.append((tag, line_num))
            out.write(f"L{line_num}: {m.group(0)} -> Depth: {len(stack)}\n")
        elif tag == 'endif' or tag == 'endfor':
            if stack:
                stack.pop()
                out.write(f"L{line_num}: {m.group(0)} -> Depth: {len(stack)}\n")
            else:
                out.write(f"L{line_num}: ERROR! {m.group(0)} WITHOUT OPENING TAG\n")
        elif tag == 'elif' or tag == 'else':
            if not stack:
                out.write(f"L{line_num}: ERROR! {m.group(0)} OUTSIDE BLOCK\n")
            else:
                out.write(f"L{line_num}: {m.group(0)} -> Depth: {len(stack)}\n")
        else:
            out.write(f"L{line_num}: {m.group(0)} -> Depth: {len(stack)}\n")

if stack:
    out.write(f"ERROR: Unclosed tags: {stack}\n")
else:
    out.write("All tags matched perfectly!\n")
out.close()
