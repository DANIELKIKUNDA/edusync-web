"""N3-G — periodic financial reports copied from the Desktop golden master (app/db/terrain.py REPORT_PROFILES,
PERIOD_LABELS; app/services/documents.py _periodic_title, _period_display, money_in_words)."""
from __future__ import annotations

from datetime import date

REPORT_PROFILES = {
    "CONSOLIDE": {"label": "Rapport financier consolidé", "title": "RAPPORT FINANCIER CONSOLIDÉ",
                  "intro": "Encaissements enregistrés pendant la période sélectionnée."},
    "INSCRIPTION_JUIN": {"label": "Inscriptions + mois de juin", "title": "RAPPORT DES INSCRIPTIONS ET DU MOIS DE JUIN",
                         "intro": "Inscriptions et paiements du mois de juin liés à l'inscription.", "fee_codes": ("INSCRIPTION", "SCOLARITE_JUIN")},
    "JOURNAL_ECUSSON": {"label": "Journal de classe + écusson", "title": "RAPPORT DES PAIEMENTS DU JOURNAL DE CLASSE ET DE L’ÉCUSSON",
                        "intro": "Paiements du journal de classe et de l'écusson.", "fee_codes": ("JOURNAL_CLASSE", "ECUSSON")},
    "FRAIS_SCOLAIRES": {"label": "Frais scolaires / mensualités", "title": "RAPPORT DES FRAIS SCOLAIRES",
                        "intro": "Paiements des frais scolaires et mensualités.", "report_group": "SCOLARITE"},
    "ARTICLES_SCOLAIRES": {"label": "Articles / tenues scolaires", "title": "RAPPORT DES ARTICLES ET TENUES SCOLAIRES",
                           "intro": "Paiements des articles et tenues scolaires (pull, uniforme et autres articles paramétrés).", "report_group": "ARTICLE"},
}
PERIOD_LABELS = {"JOURNALIER": "JOURNALIER", "HEBDOMADAIRE": "HEBDOMADAIRE", "MENSUEL": "MENSUEL", "PERSONNALISE": "PÉRIODE PERSONNALISÉE"}
MONTH_CODE_NAMES = {"01": "JANVIER", "02": "FEVRIER", "03": "MARS", "04": "AVRIL", "05": "MAI", "06": "JUIN", "07": "JUILLET", "08": "AOUT",
                    "09": "SEPTEMBRE", "10": "OCTOBRE", "11": "NOVEMBRE", "12": "DECEMBRE"}
_FR_WEEKDAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def periodic_title(profile: dict, period_type: str) -> str:
    base = str(profile.get("title") or "RAPPORT FINANCIER").strip().upper()
    period = {"JOURNALIER": "JOURNALIER", "HEBDOMADAIRE": "HEBDOMADAIRE", "MENSUEL": "MENSUEL", "PERSONNALISE": "DE PÉRIODE"}.get(period_type, period_type)
    if base == "RAPPORT FINANCIER CONSOLIDÉ":
        return f"RAPPORT FINANCIER {period} CONSOLIDÉ"
    if base.startswith("RAPPORT "):
        return f"RAPPORT {period} " + base[len("RAPPORT "):]
    return f"RAPPORT {period} — {base}"


def fr_date(value, *, with_weekday: bool = False) -> str:
    d = value if isinstance(value, date) else date.fromisoformat(str(value))
    if with_weekday:
        return f"{_FR_WEEKDAYS[d.weekday()]}, le {d.day:02d}/{d.month:02d}/{d.year}"
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def period_display(start_date, end_date, period_type: str) -> str:
    if str(start_date) == str(end_date):
        return fr_date(start_date, with_weekday=True)
    return f"Du {fr_date(start_date)} au {fr_date(end_date)}"


def _fr_under_100(n: int) -> str:
    units = ["zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf", "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize"]
    if n < 17:
        return units[n]
    if n < 20:
        return "dix-" + units[n - 10]
    if n < 70:
        tens = {20: "vingt", 30: "trente", 40: "quarante", 50: "cinquante", 60: "soixante"}
        base = (n // 10) * 10; rem = n - base
        if rem == 0:
            return tens[base]
        if rem == 1:
            return tens[base] + " et un"
        return tens[base] + "-" + _fr_under_100(rem)
    if n < 80:
        rem = n - 60
        return "soixante et onze" if rem == 11 else "soixante-" + _fr_under_100(rem)
    rem = n - 80
    if rem == 0:
        return "quatre-vingts"
    return "quatre-vingt-" + _fr_under_100(rem)


def _fr_under_1000(n: int) -> str:
    if n < 100:
        return _fr_under_100(n)
    h = n // 100; rem = n % 100
    head = "cent" if h == 1 else _fr_under_100(h) + " cent"
    if rem == 0 and h > 1:
        head += "s"
    return head if rem == 0 else head + " " + _fr_under_100(rem)


def number_to_french_words(value: int) -> str:
    n = int(value)
    if n == 0:
        return "zéro"
    if n < 0:
        return "moins " + number_to_french_words(-n)
    parts = []
    for scale, label in ((1_000_000_000, "milliard"), (1_000_000, "million"), (1000, "mille")):
        if n >= scale:
            q, n = divmod(n, scale)
            if scale == 1000:
                chunk = "mille" if q == 1 else number_to_french_words(q) + " mille"
            else:
                chunk = number_to_french_words(q) + " " + label + ("s" if q > 1 else "")
            parts.append(chunk)
    if n:
        parts.append(_fr_under_1000(n))
    return " ".join(parts)


def money_in_words(amount, currency: str) -> str:
    value = round(float(amount or 0), 2); whole = int(value); cents = int(round((value - whole) * 100))
    if currency == "CDF":
        unit = "franc congolais" if whole == 1 else "francs congolais"
    elif currency == "USD":
        unit = "dollar américain" if whole == 1 else "dollars américains"
    else:
        unit = str(currency or "")
    text = f"{number_to_french_words(whole)} {unit}"
    if cents:
        text += f" et {number_to_french_words(cents)} centime" + ("s" if cents > 1 else "")
    return text
