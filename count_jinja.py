import re

def count_tags(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Simple regex to find Jinja tags
    ifs = len(re.findall(r'\{%\s*if\s+', content))
    elifs = len(re.findall(r'\{%\s*elif\s+', content))
    elses = len(re.findall(r'\{%\s*else\s*%\}', content))
    endifs = len(re.findall(r'\{%\s*endif\s*%\}', content))
    
    # Also check blocks
    blocks = len(re.findall(r'\{%\s*block\s+', content))
    endblocks = len(re.findall(r'\{%\s*endblock\s*%\}', content))
    
    print(f"File: {filepath}")
    print(f"IFs: {ifs}")
    print(f"ELIFs: {elifs}")
    print(f"ELSEs: {elses}")
    print(f"ENDIFs: {endifs}")
    print(f"Total IF blocks (IF + ELIF + ELSE): {ifs + elifs + elses}")
    print(f"Expected ENDIFs: {ifs}") # Every IF needs an ENDIF, ELIF/ELSE are internal.
    
    if ifs != endifs:
        print("!!! MISMATCH DETECTED !!!")
    else:
        print("Tags match.")

    print(f"Blocks: {blocks}")
    print(f"Endblocks: {endblocks}")

count_tags('templates/merchant_base.html')
print("-" * 20)
count_tags('templates/merchant/onboarding.html')
