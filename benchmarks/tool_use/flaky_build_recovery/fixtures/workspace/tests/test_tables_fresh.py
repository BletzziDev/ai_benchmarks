import subprocess
import sys
from pathlib import Path

# repository root = nearest parent that contains tools/gen_tables.py
ROOT = next(p for p in Path(__file__).resolve().parents if (p / "tools" / "gen_tables.py").exists())


def test_generated_tables_are_up_to_date():
    r = subprocess.run([sys.executable, "tools/gen_tables.py", "--check"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
