"""Rapport de la semaine / du mois « qui parle comme une vraie personne » (owner, 2026-11-19).

Pure: figures in, French paragraphs out. Every sentence is built from a real figure; a missing figure removes the
sentence, nothing is ever invented. Same text for the screen, the PDF and (next step) the e-mail.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")


def week_of(day: date) -> tuple[date, date]:
    """School week: Monday → Saturday (the school does not open on Sunday)."""
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=5)


def month_of(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    nxt = (start.replace(year=start.year + 1, month=1) if start.month == 12 else start.replace(month=start.month + 1))
    return start, nxt - timedelta(days=1)


def quarter_of(day: date) -> tuple[date, date]:
    """School terms in the RDC: September–December, January–March, April–June (July–August: holidays)."""
    y, m = day.year, day.month
    if m >= 9: return date(y, 9, 1), date(y, 12, 31)
    if m <= 3: return date(y, 1, 1), date(y, 3, 31)
    if m <= 6: return date(y, 4, 1), date(y, 6, 30)
    return date(y, 7, 1), date(y, 8, 31)


def period_of(kind: str, day: date) -> tuple[date, date]:
    return {"WEEK": week_of, "MONTH": month_of, "QUARTER": quarter_of}[kind](day)


def previous_period(kind: str, start: date) -> tuple[date, date]:
    if kind == "WEEK":
        return week_of(start - timedelta(days=7))
    return period_of(kind, start - timedelta(days=1))


def fr_date(d: date, year: bool = False) -> str:
    return f"{d.day}{'er' if d.day == 1 else ''} {MOIS[d.month - 1]}" + (f" {d.year}" if year else "")


def money(v: Any, currency: str = "CDF") -> str:
    n = f"{Decimal(str(v or 0)):,.0f}".replace(",", " ")
    return f"{n} {'FC' if currency == 'CDF' else currency}"


def pct(v: Any) -> str:
    d = Decimal(str(v or 0))
    return f"{d:.0f} %" if d == d.to_integral() else f"{d:.1f} %".replace(".", ",")


@dataclass
class Digest:
    kind: str                       # WEEK | MONTH
    start: date
    end: date
    school_name: str
    scope_label: str | None = None  # « la section Secondaire » for a section reader; None = whole school
    currency: str = "CDF"
    cash: dict[str, Any] | None = None          # {total, previous, best_day: (date, amount), days: int, open_sessions: int}
    # Certification PR #109 (2026-11-20): the cash justification of the OTHER currency (USD when the letter is in FC),
    # never mixed with it — strict FC / USD separation in the attached ledger.
    other_cash: dict[str, dict[str, Any]] = field(default_factory=dict)
    recovery: dict[str, Any] | None = None      # {expected, regularized, remaining, rate}
    weakest_class: dict[str, Any] | None = None # {label, rate}
    pupils: dict[str, Any] | None = None        # {active, abandons: [..labels..], transfers: [..]}
    attention: dict[str, Any] = field(default_factory=dict)  # {reversals: n, open_sessions: n}


def title(d: Digest) -> str:
    if d.kind == "WEEK":
        return f"Votre semaine à {d.school_name} — du {fr_date(d.start)} au {fr_date(d.end, True)}"
    if d.kind == "QUARTER":
        return f"Votre trimestre ({MOIS[d.start.month - 1]} – {MOIS[d.end.month - 1]} {d.end.year}) à {d.school_name}"
    return f"Votre mois de {MOIS[d.start.month - 1]} {d.start.year} à {d.school_name}"


def greeting(civility: str | None, role_title: str | None) -> str:
    """« Bonjour Monsieur le Promoteur, » — neutral when the civility or the title is unknown."""
    if role_title and civility in ("M", "MME"):
        t = role_title.strip()
        article = "l’" if t[:1].lower() in "aeiouyéèêh" else ("le " if civility == "M" else "la ")
        return f"Bonjour {'Monsieur' if civility == 'M' else 'Madame'} {article}{t[:1].lower() + t[1:] if article == 'l’' else t},"
    return "Bonjour,"


def paragraphs(d: Digest) -> list[tuple[str, str]]:
    """(heading, text) pairs, in reading order. Headings are short; texts are full sentences."""
    out: list[tuple[str, str]] = []
    when = {"WEEK": "cette semaine", "MONTH": "ce mois-ci", "QUARTER": "ce trimestre"}[d.kind]
    where = d.scope_label or d.school_name
    period = {"WEEK": "e la semaine", "MONTH": " le mois", "QUARTER": " le trimestre"}[d.kind]
    out.append(("", f"Voici comment s’est passé{period} à {where.rstrip('.')}."))
    c = d.cash
    if c is not None:
        total = Decimal(str(c.get("total") or 0))
        if total > 0:
            s = f"L’école a encaissé {money(total, d.currency)} {when}"
            prev = Decimal(str(c.get("previous") or 0))
            if prev > 0:
                diff = (total - prev) * 100 / prev
                if abs(diff) < 1:
                    s += ", à peu près comme la période précédente"
                else:
                    s += f", soit {pct(round(abs(diff)))} de {'plus' if diff > 0 else 'moins'} que la période précédente"
            s += "."
            best = c.get("best_day")
            if best and d.kind == "WEEK":
                s += f" Le meilleur jour a été {JOURS[best[0].weekday()]} ({money(best[1], d.currency)})."
            out.append(("L’argent", s))
        else:
            out.append(("L’argent", f"Aucun encaissement n’a été enregistré {when}."))
    r = d.recovery
    if r is not None and Decimal(str(r.get("expected") or 0)) > 0:
        s = (f"Depuis la rentrée, {pct(r['rate'])} de ce qui était attendu est rentré"
             f"{' dans votre section' if d.scope_label else ''}. Il reste {money(r['remaining'], d.currency)} à recouvrer.")
        w = d.weakest_class
        if w and Decimal(str(w.get("rate") or 0)) < Decimal(str(r.get("rate") or 0)):
            s += f" La classe la plus en retard est la {w['label']} ({pct(w['rate'])}) : un rappel aux familles serait utile."
        out.append(("Le recouvrement", s))
    p = d.pupils
    if p is not None:
        s = f"{p['active']} élève{'s' if p['active'] > 1 else ''} actif{'s' if p['active'] > 1 else ''}."
        ab, tr = p.get("abandons") or [], p.get("transfers") or []
        if not ab and not tr:
            s += f" Aucun abandon ni transfert {when}."
        else:
            if ab:
                s += f" {len(ab)} abandon{'s' if len(ab) > 1 else ''} {when} ({', '.join(ab[:4])}{'…' if len(ab) > 4 else ''})."
            if tr:
                s += f" {len(tr)} transfert{'s' if len(tr) > 1 else ''} vers une autre école ({', '.join(tr[:4])}{'…' if len(tr) > 4 else ''})."
        out.append(("Les élèves", s))
    a = d.attention
    points = []
    if a.get("reversals"):
        n = a["reversals"]; points.append(f"{n} reçu{'s' if n > 1 else ''} annulé{'s' if n > 1 else ''}")
    if a.get("open_sessions"):
        n = a["open_sessions"]; points.append(f"{n} caisse{'s' if n > 1 else ''} d’un jour passé encore ouverte{'s' if n > 1 else ''}")
    if a.get("variances"):
        n = a["variances"]; points.append(f"{n} clôture{'s' if n > 1 else ''} de caisse avec un écart")
    if points:
        out.append(("À surveiller", f"{'; '.join(points)[:1].upper()}{'; '.join(points)[1:]}."))
    elif c is not None:
        out.append(("À surveiller", "Rien d’anormal à signaler : aucune annulation de reçu et aucune caisse restée ouverte."))
    return out
