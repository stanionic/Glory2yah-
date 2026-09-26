"""Standalone static validation for the Jere Biznis module (auto-admin + co-admins).

Run:
    python _validate_jere_biznis.py

Exit code:
    0  -> every check PASSED
    1  -> at least one FAIL / exception

This validator does NOT boot Flask/Redis. It inspects source files (AST + text)
to confirm the module is correctly wired: models, endpoints, billing, roles,
offline sync, isolation, and that the rest of the app is not impacted.
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
errors = []


def section(title):
    print("=" * 64)
    print(title)
    print("=" * 64)


def ck(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    line = f"[{status}] {label}"
    if detail:
        line += f"\n    -> {detail}"
    print(line)
    if not ok:
        errors.append(label)


def check_file_exists(rel_path, label):
    p = ROOT / rel_path
    if not p.is_file():
        ck(label, False, f"missing: {rel_path}")
        return None
    return p


def parse_python(p, label):
    try:
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)
        return src, tree
    except SyntaxError as e:
        ck(label, False, f"AST parse error: {e}")
        return None, None
    except Exception as e:
        ck(label, False, f"cannot read/parse {p}: {e}")
        return None, None
