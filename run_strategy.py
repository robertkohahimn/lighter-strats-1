#!/usr/bin/env python3
"""
Command-line runner for Lighter Trading Strategy
"""

import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lighter_strategy.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())