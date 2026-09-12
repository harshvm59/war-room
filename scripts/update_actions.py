#!/usr/bin/env python3
"""Compatibility entry point: action cards use the free daily technical pipeline.

The old paid-model action generator is retired. This entry point makes no AI call.
"""
import sys
from analyze_daily import main

if __name__ == "__main__":
    sys.exit(main())
