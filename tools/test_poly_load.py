#!/usr/bin/env python3
"""Load validation through installed cache and real stock native-load callers."""
from test_poly_module_only import test_load_validation, test_native_load
if __name__ == '__main__':
    test_load_validation()
    print('PASS exact/short/long/missing/garbage/read-error/close-error sidecars, tracks 1..3')
    test_native_load()
    print('PASS real native loader and 24-letter preload, including missing native')
