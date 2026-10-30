"""Certification Responsable financier (2026-10-28): « Relevé PDF » answered HTTP 500 for every role —
finance_reports/api/router.py called archive_generated_tx without importing it (NameError at run time only).

Static guard with the standard library (symtable): in every backend module, a global name READ inside a function must
be defined at module level (import, def, class, assignment) or be a builtin. Catches a missing import before any user does.
"""
from __future__ import annotations

import builtins
import symtable
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def _module_names(table: symtable.SymbolTable) -> set[str]:
    return {s.get_name() for s in table.get_symbols() if s.is_assigned() or s.is_imported() or s.is_namespace()}


def _global_reads(table: symtable.SymbolTable):
    for child in table.get_children():
        if child.get_type() in ("function", "class"):
            for sym in child.get_symbols():
                if sym.is_referenced() and (sym.is_global() or (child.get_type() == "class" and not sym.is_assigned() and not sym.is_local())):
                    yield child.get_name(), sym.get_name()
        yield from _global_reads(child)


def test_every_global_name_read_in_a_function_is_defined():
    known_builtins = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__", "__package__", "__builtins__"}
    missing = []
    for path in sorted(SRC.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "import *" in source:  # star imports cannot be resolved statically
            continue
        table = symtable.symtable(source, str(path), "exec")
        defined = _module_names(table) | known_builtins
        for scope, name in _global_reads(table):
            if name not in defined:
                missing.append(f"{path.relative_to(SRC)}: {scope}() lit « {name} », jamais défini ni importé")
    assert missing == [], "\n".join(sorted(set(missing)))
