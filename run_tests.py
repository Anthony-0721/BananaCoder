#!/usr/bin/env python3
"""Test runner: runs tests with coverage and generates reports.

Usage:
    python run_tests.py              # Run tests with coverage report
    python run_tests.py --html       # Run tests + generate HTML report
    python run_tests.py --quick      # Run tests only, no coverage
"""
import sys
import subprocess
from pathlib import Path

BASE = Path(__file__).parent


def run_tests(html=False, quick=False):
    if quick:
        cmd = [sys.executable, "-m", "pytest", "tests/", "-q"]
        result = subprocess.run(cmd)
    else:
        print("=== Running tests with coverage ===")
        result = subprocess.run([
            sys.executable, "-m", "coverage", "run", "-m", "pytest", "tests/", "-q",
        ])
        if result.returncode == 0:
            print("\n=== Coverage report ===")
            subprocess.run([
                sys.executable, "-m", "coverage", "report",
                "--include=banana/*", "--omit=*/__init__.py,*/__main__.py",
                "--show-missing",
            ])
            if html:
                subprocess.run([
                    sys.executable, "-m", "coverage", "html",
                    "--include=banana/*", "-d", "coverage_html",
                ])
                print("\n[OK] HTML report: coverage_html/index.html")

    if result.returncode != 0:
        print(f"\n[FAILED] Tests failed (exit {result.returncode})")
        sys.exit(result.returncode)
    else:
        print("\n[OK] All tests passed")


def main():
    args = set(sys.argv[1:])
    run_tests(html="--html" in args, quick="--quick" in args)


if __name__ == "__main__":
    main()
