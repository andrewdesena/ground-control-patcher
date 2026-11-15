#!/usr/bin/env python3
"""Save through installed hooks and the real stock pattern writer."""
from test_poly_module_only import test_banks_save, test_clear_delete_copy
if __name__ == '__main__':
    test_banks_save()
    print('PASS correct melodic bank for A/B/C/D/X; drums never get sidecars')
    test_clear_delete_copy()
    print('PASS clear/save zeros, independent copy, native delete removes sidecar')
