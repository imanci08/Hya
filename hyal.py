"""Compatibility import/launcher for integrations created before the Hya rename."""
if __name__ == '__main__':
    import runpy
    runpy.run_module('hya', run_name='__main__')
else:
    import sys
    import hya
    sys.modules[__name__] = hya
