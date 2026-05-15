import sys
import traceback

try:
    import merchant.ai_engine
    print("SUCCESS merchant.ai_engine imported correctly")
except Exception as e:
    print("FAILED to import")
    traceback.print_exc()
