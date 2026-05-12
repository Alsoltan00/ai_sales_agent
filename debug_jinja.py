import jinja2
import os

template_dir = 'templates'
env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))

try:
    template = env.get_template('merchant/onboarding.html')
    print("Template parsed successfully!")
except jinja2.exceptions.TemplateSyntaxError as e:
    print(f"Syntax Error: {e}")
    print(f"File: {e.filename}")
    print(f"Line: {e.lineno}")
except Exception as e:
    print(f"Error: {e}")
