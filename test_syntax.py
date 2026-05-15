import py_compile
import traceback
try:
    py_compile.compile('merchant/router.py', doraise=True)
    print("ROUTER COMPILED SUCCESS")
except Exception as e:
    traceback.print_exc()
