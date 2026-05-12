import sys
import traceback
from jinja2 import Environment, FileSystemLoader

try:
    env = Environment(loader=FileSystemLoader('templates'))
    env.get_template('merchant_base.html')
    print("OK")
except Exception as e:
    with open('jinja_err.txt', 'w') as f:
        f.write(traceback.format_exc())
