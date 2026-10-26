"""Run the whole project from scratch:  python run_all.py"""
import subprocess
import sys
from pathlib import Path

for step in ("src/download.py", "src/build_db.py", "src/analysis.py", "src/make_notebook.py"):
    print(f"\n=== {step}")
    subprocess.run([sys.executable, step], check=True, cwd=Path(__file__).parent)
