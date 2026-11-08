# SPDX-License-Identifier: MIT
"""Checks that every po/*.po translates each string the app marks with _() or ngettext()."""

import ast
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
SOURCE = os.path.join(ROOT, "owly_drop.py")

spec = importlib.util.spec_from_file_location("owly_drop", SOURCE)
owly_drop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(owly_drop)

wanted = set()
for node in ast.walk(ast.parse(open(SOURCE, encoding="utf-8").read())):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        args = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
        if node.func.id == "_" and args:
            wanted.add(args[0])
        elif node.func.id == "ngettext" and len(args) >= 2:
            wanted.add((args[0], args[1]))

ok = True
for name in sorted(os.listdir(os.path.join(ROOT, "po"))):
    entries = owly_drop.parse_po(os.path.join(ROOT, "po", name))
    missing = sorted(map(str, wanted - entries.keys()))
    unused = sorted(map(str, entries.keys() - wanted))
    print(f"{name}: {len(wanted) - len(missing)}/{len(wanted)} translated")
    for m in missing:
        print(f"  missing: {m}")
    for u in unused:
        print(f"  unused:  {u}")
    ok = ok and not missing
sys.exit(0 if ok else 1)
