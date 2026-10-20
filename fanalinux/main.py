#!/usr/bin/env python3
"""
FanaLinux - Main Entrypoint
"""

import sys
import os

# Ensure package root is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from fanalinux.ui.app import run_app

if __name__ == "__main__":
    sys.exit(run_app())
