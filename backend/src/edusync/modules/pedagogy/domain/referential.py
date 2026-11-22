"""Official MINEDUC referential — pure rules (no database), unit-tested.

* reading + validating the versioned files of reference/<version>/ (counts, references, weighting rules);
* the owner rule « l'examen est toujours le double de la période » (2026-11-22);
* suggestion of the official class for a class of the school (P1 → 1PR, H1 + option CG → 1CG…). EduSync only SUGGESTS:
  the school confirms every link.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

REFERENCE_DIR = Path(__file__).resolve().parents[1] / "reference"
CURRENT_VERSION = "MINEDUC-2024-2025-V2"
FILES = ("sections.json", "options.json", "classes.json", "courses.json", "programmes.json")
MAX_KEYS = ("max_p1", "max_p2", "max_ex1", "max_p3", "max_p4", "max_ex2", "max_p5", "max_p6", "max_ex3")
GROUP_LABEL = {"GENERAL": "Options générales", "GROUPE_1": "Technique — Groupe 1", "GROUPE_2": "Technique — Groupe 2"}
# EduSync level codes (rdc_reference_classes) → official class code (non-humanities) or level digit (humanities)
LEVEL_TO_OFFICIAL = {"M1": "1MAT", "M2": "2MAT", "M3": "3MAT", "P1": "1PR", "P2": "2PR", "P3": "3PR", "P4": "4PR", "P5": "5PR",
                     "P6": "6PR", "S7": "7EB", "S8": "8EB"}
HUMANITIES = {"H1": "1", "H2": "2", "H3": "3", "H4": "4"}
# Option codes used by EduSync before the official list (settings wizard ≤ 2026-11-22) → official sigle.
LEGACY_OPTION_SIGLE = {"ELECTRONIQUE": "EI", "CONSTRUCTION": "CONS", "NUTRITION": "NUT"}


class ReferentialError(ValueError):
    pass


@dataclass(frozen=True)
class Referential:
    version: str
    meta: dict
    sections: list[dict]
    options: list[dict]
    classes: list[dict]
    courses: list[dict]
    programmes: list[dict]
    checksum: str

    @property
    def line_count(self) -> int:
        return sum(len(p["lines"]) for p in self.programmes)


def exam_is_double(max_: list[int]) -> bool:
    """Owner rule: EX1 = 2×P1, EX2 = 2×P3, EX3 = 2×P5 (a term's two periods weigh the same)."""
    return max_[2] == 2 * max_[0] and max_[5] == 2 * max_[3] and max_[8] == 2 * max_[6]


def check_line(class_code: str, structure: str, line: dict) -> None:
    m = line["max"]
    where = f"{class_code} / {line['course']}"
    if len(m) != 9 or any(not isinstance(v, int) or v < 0 for v in m) or sum(m) <= 0:
        raise ReferentialError(f"{where} : maxima invalides {m}")
    if structure == "SEMESTRIEL" and (m[6] or m[7] or m[8]):
        raise ReferentialError(f"{where} : une classe semestrielle n’a ni P5, ni P6, ni EX3")
    if line["exam"] and not exam_is_double(m):
        raise ReferentialError(f"{where} : l’examen doit valoir le double de la période {m}")
    if not line["exam"] and (m[2] or m[5] or m[8]):
        raise ReferentialError(f"{where} : un cours sans examen n’a aucun point d’examen")


def load(version: str = CURRENT_VERSION, base: Path = REFERENCE_DIR) -> Referential:
    folder = base / version
    raw = {name: (folder / name).read_bytes() for name in FILES}
    data = {name: json.loads(raw[name].decode("utf-8")) for name in FILES}
    digest = hashlib.sha256(b"".join(raw[name] for name in FILES)).hexdigest()
    ref = Referential(version=version, meta=data["programmes.json"].get("meta", {}),
                      sections=data["sections.json"]["items"], options=data["options.json"]["items"],
                      classes=data["classes.json"]["items"], courses=data["courses.json"]["items"],
                      programmes=data["programmes.json"]["items"], checksum=digest)
    validate(ref)
    return ref


def validate(ref: Referential) -> None:
    if ref.meta.get("version") != ref.version:
        raise ReferentialError("Version du fichier des programmes différente du dossier")
    sections = {s["code"] for s in ref.sections}
    options = {o["code"] for o in ref.options}
    if len({o["sigle"] for o in ref.options}) != len(ref.options):
        raise ReferentialError("Sigle d’option en double")
    classes = {}
    for c in ref.classes:
        if c["section"] not in sections or (c["option"] is not None and c["option"] not in options):
            raise ReferentialError(f"Classe {c['code']} : section ou option inconnue")
        if (c["cycle"] == "HUMANITE") != (c["option"] is not None):
            raise ReferentialError(f"Classe {c['code']} : seules les humanités ont une option")
        classes[c["code"]] = c
    courses = {c["code"] for c in ref.courses}
    seen_classes = set()
    for p in ref.programmes:
        cls = classes.get(p["class"])
        if cls is None or p["class"] in seen_classes:
            raise ReferentialError(f"Programme {p['class']} : classe inconnue ou en double")
        seen_classes.add(p["class"])
        if p["structure"] != cls["structure"]:
            raise ReferentialError(f"Programme {p['class']} : structure différente de la classe")
        seen_courses = set()
        for line in p["lines"]:
            if line["course"] not in courses or line["course"] in seen_courses:
                raise ReferentialError(f"Programme {p['class']} : cours {line['course']} inconnu ou en double")
            seen_courses.add(line["course"])
            check_line(p["class"], p["structure"], line)


def suggest_official_class(level_code: str | None, option_code: str | None, official_sigles: set[str]) -> str | None:
    """Official class suggested for a school class: its level (P1, H2…) and, in the humanities, its option code."""
    level = (level_code or "").strip().upper()
    if level in LEVEL_TO_OFFICIAL:
        return LEVEL_TO_OFFICIAL[level]
    if level in HUMANITIES and option_code:
        code = option_code.strip().upper()
        sigle = LEGACY_OPTION_SIGLE.get(code, code)
        if sigle in official_sigles:
            return HUMANITIES[level] + sigle
    return None


def totals(lines: list[dict]) -> dict[str, int]:
    """Sum of the maxima of a programme per column (calculable lines only) — the bulletin's « Maxima généraux »."""
    out = dict.fromkeys(MAX_KEYS, 0)
    for line in lines:
        if line.get("calculable", True):
            for k in MAX_KEYS:
                out[k] += int(line[k])
    return out
