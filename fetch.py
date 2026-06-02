#!/usr/bin/env python3
"""入口：python fetch.py <牌谱链接> [...]"""
import sys
from src.fetcher.cli import main

if __name__ == "__main__":
    sys.exit(main())
