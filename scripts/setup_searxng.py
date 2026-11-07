#!/usr/bin/env python3
"""
setup_searxng.py - Setup local SearXNG environment for Aquila AI Framework (Zero Docker)
"""

import sys
import subprocess

def main():
    print("[Aquila SearXNG] Checking local Python environment...")
    required = ["httpx", "urllib3", "searxng"]
    for pkg in required:
        try:
            __import__(pkg)
            print(f"  [OK] {pkg} is already installed.")
        except ImportError:
            print(f"  [..] Installing {pkg}...")
            cmd = [sys.executable, "-m", "pip", "install", pkg]
            subprocess.check_call(cmd)
            print(f"  [OK] {pkg} installed successfully.")

    print("\n[Aquila SearXNG] Setup complete! You can now start the server with:")
    print("  python scripts/run_searxng.py")

if __name__ == "__main__":
    main()

