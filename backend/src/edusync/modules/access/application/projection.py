"""Authoritative projection of the school space for the signed-in member (owner decision 8, 2026-10-23).

The frontend no longer guesses: navigation, dashboard widgets and shortcuts are computed here from the EFFECTIVE
capabilities (standard role + school policy, exceptions, aliases, scopes). Each entry declares the capabilities it
needs: `all` (every one) and/or `any` (at least one). The backend remains the final authority on every endpoint;
this projection only decides what is worth showing.
"""
from __future__ import annotations

# (key, label, icon, any-of capabilities) — `home` is always present.
NAVIGATION: list[tuple[str, str, str, tuple[str, ...]]] = [
    ("home", "Accueil", "home", ()),
    ("settings", "Paramètres", "settings", (
        "settings.school_identity.read", "settings.structure.read", "settings.academic_year.read", "settings.tariffs.read",
        "settings.fee_types.read", "settings.payment_policy.read", "settings.documents.read", "settings.products.read",
        "settings.contributions.read", "settings.benefits.read", "settings.enrollment_policy.read", "settings.backups.read",
        "finance.anticipation_plans.read")),
    ("personnel", "Personnel", "users", ("personnel.read",)),
    ("students", "Élèves & inscriptions", "students", ("students.read", "families.read")),
    ("headcounts", "Effectifs & dépôts", "chart", ("headcounts.read", "contributions.read", "contributions.register.read")),
    ("finance", "Centre financier", "finance", (
        "finance.cash.read", "finance.checkout.search", "finance.receipts.read", "finance.recovery.monthly.read",
        "finance.reports.history.read", "finance.decisions.read", "finance.advance_funds.read", "finance.cash.other.read",
        "finance.products.read", "finance.analysis.by_fee.read")),
    ("documents", "Documents", "folder", (
        "documents.history.read", "documents.open", "students.directory.export", "families.directory.export",
        "personnel.directory.export", "headcounts.export", "finance.views.vf01.export", "finance.reports.periodic.export",
        "students.account.export")),
    ("stewardship", "Intendance", "box", ("inventory.assets.read", "inventory.stock.read", "inventory.counts.read")),
    ("sync", "Synchronisation", "sync", ("sync.status.read",)),
    ("communications", "Communication", "bell", ("communications.read", "notifications.internal.configure")),
    ("access", "Accès & rôles", "lock", ("access.users.read", "access.roles.read", "audit.school.read")),
]

# Dashboard widgets: id, title, module opened by « Voir », priority (lower first), all-of, any-of.
WIDGETS: list[dict] = [
    # Administration / configuration — « what must the administrator watch and do today »
    {"id": "access.members", "title": "Comptes et accès", "module": "access", "priority": 10, "all": ("access.users.read",)},
    {"id": "access.requests", "title": "Demandes d’approbation", "module": "access", "priority": 11, "all": ("access.roles.manage",)},
    # Setup journey and its shortcut only for whoever can change the settings (2026-10-24: a cashier only reads them).
    {"id": "settings.readiness", "title": "Paramétrage de l’établissement", "module": "settings", "priority": 12, "all": ("settings.school_identity.update",)},
    # Each role its own home (owner, 2026-10-24): administration cards need a MANAGEMENT right, never a mere read right
    # (the cashier reads the year and the structure through the secretariat baseline but administers neither).
    {"id": "settings.academic_year", "title": "Année scolaire", "module": "settings", "priority": 13, "all": ("settings.academic_year.update",)},
    {"id": "settings.structure", "title": "Structure : sections et classes", "module": "settings", "priority": 14, "all": ("settings.classes.create",)},
    {"id": "audit.recent", "title": "Dernières actions administratives", "module": "access", "priority": 15, "all": ("audit.school.read",)},
    {"id": "sync.devices", "title": "Appareils et synchronisation", "module": "sync", "priority": 16, "all": ("sync.device.register",)},
    # Operations
    {"id": "cash.today", "title": "Ma caisse du jour", "module": "finance", "priority": 20, "all": ("finance.cash.read", "finance.cash.open")},
    {"id": "cash.supervision", "title": "Situation des caisses", "module": "finance", "priority": 20, "all": ("finance.cash.other.read",)},
    {"id": "checkout.quick", "title": "Encaisser rapidement", "module": "finance", "priority": 21, "all": ("finance.checkout.collect",)},
    # Desk (cashier, who is usually also the secretary in the DRC): today's receipts, enrollments, articles to watch.
    {"id": "cash.receipts", "title": "Encaissements du jour", "module": "finance", "priority": 22, "all": ("finance.cash.read", "finance.receipts.read")},
    {"id": "enrollments.today", "title": "Inscriptions", "module": "students", "priority": 23, "all": ("enrollments.create", "students.read")},
    {"id": "products.watch", "title": "Articles à surveiller", "module": "finance", "priority": 24, "all": ("finance.products.sale",)},
    # breakdowns: the groupings the card may load, decided here from the capabilities (never guessed in the browser).
    {"id": "headcounts.summary", "title": "Effectifs", "module": "headcounts", "priority": 30, "all": ("headcounts.read",),
     "breakdowns": (("section", "headcounts.by_section.read"), ("class", "headcounts.by_class.read"), ("option", "headcounts.by_option.read"))},
    {"id": "headcounts.movements", "title": "Mouvements récents", "module": "headcounts", "priority": 31, "all": ("headcounts.movements.read",)},
    {"id": "personnel.summary", "title": "Personnel", "module": "personnel", "priority": 32, "all": ("personnel.summary.read",)},
    {"id": "finance.recovery", "title": "Évolution du recouvrement", "module": "finance", "priority": 40, "all": ("finance.recovery.monthly.read",)},
    {"id": "finance.by_fee", "title": "Situation par familles de frais", "module": "finance", "priority": 41, "all": ("finance.analysis.by_fee.read",)},
    {"id": "finance.decisions", "title": "Décisions financières actives", "module": "finance", "priority": 42, "all": ("finance.decisions.read",)},
    # school_scope: the read model behind the card is school-wide only (official reports, archived documents without
    # section provenance) — the API refuses a section-only grant, so the card is not offered to it (PR #27).
    {"id": "reports.latest", "title": "Rapports officiels récents", "module": "finance", "priority": 43, "all": ("finance.reports.history.read",), "school_scope": True},
    {"id": "documents.recent", "title": "Documents récents", "module": "documents", "priority": 44, "all": ("documents.history.read",), "school_scope": True},
    {"id": "inventory.stock", "title": "Stocks", "module": "stewardship", "priority": 50, "all": ("inventory.stock.read",)},
    {"id": "inventory.counts", "title": "Inventaires", "module": "stewardship", "priority": 51, "all": ("inventory.counts.read",)},
]

# Shortcuts offered on the home screen / header.
ACTIONS: list[dict] = [
    {"id": "students.search", "label": "Rechercher un élève", "module": "students", "all": ("students.read",)},
    {"id": "cash.supervise", "label": "Superviser les caisses", "module": "finance", "all": ("finance.cash.other.read",)},
    {"id": "reports.open", "label": "Rapports financiers", "module": "finance", "all": ("finance.reports.history.read",)},
    {"id": "checkout.new", "label": "Nouvel encaissement", "module": "finance", "all": ("finance.checkout.collect",)},
    {"id": "enrollments.new", "label": "Nouvelle inscription", "module": "students", "all": ("enrollments.create",)},
    {"id": "members.create", "label": "Ajouter un utilisateur", "module": "access", "all": ("access.users.create",)},
    {"id": "settings.open", "label": "Compléter le paramétrage", "module": "settings", "all": ("settings.school_identity.update",)},
    {"id": "inventory.open", "label": "Ouvrir l’intendance", "module": "stewardship", "all": ("inventory.stock.read",)},
]


def _allowed(entry: dict, caps: set[str]) -> bool:
    return all(c in caps for c in entry.get("all", ())) and (not entry.get("any") or any(c in caps for c in entry["any"]))


def navigation(caps: set[str]) -> list[dict]:
    return [{"key": k, "label": label, "icon": icon} for k, label, icon, any_of in NAVIGATION if not any_of or any(c in caps for c in any_of)]


def widgets(caps: set[str], school_caps: set[str] | None = None) -> list[dict]:
    """school_caps: capabilities held with a SCHOOL scope (None = every capability is school-wide)."""
    out = []
    for w in sorted(WIDGETS, key=lambda w: w["priority"]):
        if not _allowed(w, caps) or (w.get("school_scope") and school_caps is not None and not _allowed(w, school_caps)):
            continue
        item = {k: v for k, v in w.items() if k not in ("all", "any", "breakdowns", "school_scope")}
        if "breakdowns" in w:
            item["breakdowns"] = [group for group, cap in w["breakdowns"] if cap in caps]
        out.append(item)
    return out


def actions(caps: set[str]) -> list[dict]:
    return [{k: v for k, v in a.items() if k not in ("all", "any")} for a in ACTIONS if _allowed(a, caps)]


def declared_capabilities() -> set[str]:
    """Every capability the projection relies on (checked against the registry by the tests)."""
    out = {c for _, _, _, any_of in NAVIGATION for c in any_of}
    for entry in WIDGETS + ACTIONS:
        out |= set(entry.get("all", ())) | set(entry.get("any", ())) | {cap for _, cap in entry.get("breakdowns", ())}
    return out
