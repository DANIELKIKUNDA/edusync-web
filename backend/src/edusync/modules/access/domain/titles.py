"""Titles shown for a member's role (owner, 2026-11-09).

« Lorsque la personne est une femme : Promotrice, Directrice… » and « directeur du primaire, directrice de la maternelle,
ou une seule personne pour les deux ». The ROLE never changes (same capabilities, same scopes); only the words shown on
the home page, in the members list and — later — on signed documents (« La Directrice ») follow the person's civility
(set per school membership: M / MME, unknown = neutral wording) and the sections of a section-bound role.
"""
from __future__ import annotations

# code → (masculine, feminine). Roles absent here are epicene (Gestionnaire, Secrétariat…) and keep their label.
TITLES: dict[str, tuple[str, str]] = {
    "PROMOTEUR": ("Promoteur", "Promotrice"),
    "PREFET_ETUDES": ("Préfet des études", "Préfète des études"),
    "DIRECTEUR_ETUDES": ("Directeur des études", "Directrice des études"),
    "DIRECTEUR_DISCIPLINE": ("Directeur de discipline", "Directrice de discipline"),
    "DIRECTION_SECTION": ("Directeur", "Directrice"),
    "CAISSIER": ("Caissier", "Caissière"),
    "INTENDANT": ("Intendant", "Intendante"),
    "ADMIN_SYSTEME_ECOLE": ("Administrateur système école", "Administratrice système école"),
    "RESPONSABLE_FINANCE": ("Responsable chargé des finances", "Responsable chargée des finances"),
}
CIVILITIES = ("M", "MME")
# Sections named in a title, with their French article; any other section reads « de la section X ».
_SECTION_PHRASE = {"MATERNELLE": "de la maternelle", "PRIMAIRE": "du primaire", "SECONDAIRE": "du secondaire"}
_SECTION_ORDER = {"MATERNELLE": 0, "PRIMAIRE": 1, "SECONDAIRE": 2}


def section_phrase(sections: list[tuple[str, str | None]]) -> str:
    """[(code, label)] → « du primaire et de la maternelle » (school order: maternelle, primaire, secondaire)."""
    seen: dict[str, str] = {}
    for code, label in sections:
        c = (code or "").strip().upper()
        lab = (label or "").strip().upper()
        if c not in _SECTION_PHRASE and lab in _SECTION_PHRASE:   # school codes like « MAT » named « Maternelle »
            c = lab
        if c and c not in seen:
            seen[c] = _SECTION_PHRASE.get(c) or f"de la section {(label or c).strip()}"
    parts = [seen[c] for c in sorted(seen, key=lambda c: (_SECTION_ORDER.get(c, 9), c))]
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " et " + parts[-1]


def role_title(code: str | None, kind: str | None, label: str, civility: str | None = None,
               sections: list[tuple[str, str | None]] | None = None) -> str:
    """Words for one role of one member. A school's own role (SCHOOL_CUSTOM) keeps the name the school gave it."""
    if kind == "SCHOOL_CUSTOM" or not code:
        return label
    civ = (civility or "").upper()
    if code == "DIRECTION_SECTION":
        where = section_phrase(sections or [])
        if civ in CIVILITIES:
            head = TITLES[code][1 if civ == "MME" else 0]
            return f"{head} {where}" if where else f"{head} de section"
        return f"Direction {where}" if where else label        # civility unknown: neutral « Direction du primaire »
    pair = TITLES.get(code)
    if not pair or civ not in CIVILITIES:
        return label
    return pair[1 if civ == "MME" else 0]
