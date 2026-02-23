import importlib, sys
try:
    importlib.import_module('handlers.receipt')
    print('OK')
except Exception as e:
    print('IMPORT ERROR:', e)
    sys.exit(1)
