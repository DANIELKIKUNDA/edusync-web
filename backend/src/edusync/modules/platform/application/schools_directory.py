"""Module Écoles (plateforme), lot 2026-10: directory queries and identity helpers. No business rule changes.

* Statuses stay exactly ACTIVE / SUSPENDED / DISABLED (schools.status CHECK constraint).
* "Configuration" is a separate onboarding state derived from existing data only:
    ADMIN_MISSING  no active ADMIN_SYSTEME_ECOLE assignment in the school (same definition as the dashboard item)
    ADMIN_PENDING  administrator(s) assigned but none activated yet (temporary password not replaced, or open invitation)
    INCOMPLETE     an administrator is active but a readiness gate is missing (année scolaire, classes, catalogue des frais)
    COMPLETE       every readiness gate of the school sheet is met
  The readiness gates are the ones of the existing school sheet; platform_school_setup() (migration 0078) returns
  their three booleans without exposing any row of the school settings tables.
* "Dernière activité" = most recent activity (last_seen_at) of a device session opened in the school space.
* Pagination is keyset (cursor) on a stable order ending with the primary key: no duplicate, no skipped row.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import datetime
from uuid import UUID

from sqlalchemy import text

SCHOOL_ADMIN_ROLE = "ADMIN_SYSTEME_ECOLE"

# The 26 provinces of the DR Congo (constitution of 2006, effective 2015). Stored as written here (stable value).
RDC_PROVINCES = (
    "Bas-Uele", "Équateur", "Haut-Katanga", "Haut-Lomami", "Haut-Uele", "Ituri", "Kasaï", "Kasaï-Central", "Kasaï-Oriental",
    "Kinshasa", "Kongo-Central", "Kwango", "Kwilu", "Lomami", "Lualaba", "Mai-Ndombe", "Maniema", "Mongala", "Nord-Kivu",
    "Nord-Ubangi", "Sankuru", "Sud-Kivu", "Sud-Ubangi", "Tanganyika", "Tshopo", "Tshuapa",
)
# Chef-lieu of each province (official): the only cities proposed by default; any other locality can be typed.
PROVINCE_CAPITALS = {
    "Bas-Uele": "Buta", "Équateur": "Mbandaka", "Haut-Katanga": "Lubumbashi", "Haut-Lomami": "Kamina", "Haut-Uele": "Isiro",
    "Ituri": "Bunia", "Kasaï": "Tshikapa", "Kasaï-Central": "Kananga", "Kasaï-Oriental": "Mbuji-Mayi", "Kinshasa": "Kinshasa",
    "Kongo-Central": "Matadi", "Kwango": "Kenge", "Kwilu": "Bandundu", "Lomami": "Kabinda", "Lualaba": "Kolwezi",
    "Mai-Ndombe": "Inongo", "Maniema": "Kindu", "Mongala": "Lisala", "Nord-Kivu": "Goma", "Nord-Ubangi": "Gbadolite",
    "Sankuru": "Lusambo", "Sud-Kivu": "Bukavu", "Sud-Ubangi": "Gemena", "Tanganyika": "Kalemie", "Tshopo": "Kisangani",
    "Tshuapa": "Boende",
}
CONFIG_STATES = ("COMPLETE", "INCOMPLETE", "ADMIN_PENDING", "ADMIN_MISSING")
SORTS = ("name", "created", "status")
STATUS_ORDER = "CASE s.status WHEN 'ACTIVE' THEN 1 WHEN 'SUSPENDED' THEN 2 ELSE 3 END"


def _fold(value: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c)).lower().replace(" ", "").replace("-", "")


def normalize_province(value: str | None) -> str | None:
    """Canonical province name from the reference list (accents, case, spaces, hyphens tolerated), else ValueError."""
    if value is None or not value.strip():
        return None
    wanted = _fold(value)
    for p in RDC_PROVINCES:
        if _fold(p) == wanted:
            return p
    raise ValueError("Province inconnue : choisissez l’une des 26 provinces de la RDC.")


def normalize_phone(value: str | None) -> str | None:
    """Canonical E.164. DR Congo numbers (+243 then 9 digits) accept 0XXXXXXXXX, 243..., +243..., spaces, dots, dashes;
    other countries must be written with their + prefix. Raises ValueError for anything else."""
    if value is None or not value.strip():
        return None
    raw = value.strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+") and not raw.startswith("+243"):
        if 8 <= len(digits) <= 15:
            return "+" + digits
        raise ValueError("Numéro de téléphone invalide.")
    if digits.startswith("00243"):
        digits = digits[5:]
    elif digits.startswith("243"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 9 or digits[0] not in "89":
        raise ValueError("Numéro RDC invalide : 9 chiffres après +243 (ex. : +243 81 234 5678).")
    return "+243" + digits


def format_phone(canonical: str | None) -> str | None:
    if not canonical:
        return canonical
    m = re.fullmatch(r"\+243(\d{2})(\d{3})(\d{4})", canonical)
    return f"+243 {m.group(1)} {m.group(2)} {m.group(3)}" if m else canonical


def next_school_code(conn) -> str:
    """EDS-000001, EDS-000002... from a database sequence (transactional, unique); skips a code already taken."""
    for _ in range(20):
        code = "EDS-" + str(int(conn.execute(text("SELECT nextval('school_code_seq')")).scalar_one())).zfill(6)
        if conn.execute(text("SELECT 1 FROM schools WHERE code=:c"), {"c": code}).first() is None:
            return code
    raise RuntimeError("Génération du code école impossible")


# ---------------------------------------------------------------- directory list (keyset pagination)
_BASE_TEMPLATE = f"""
WITH base AS (
  SELECT s.id, s.code, s.name, s.status, s.province, s.city, s.contact_name, s.contact_phone, s.created_at,
         {STATUS_ORDER} AS status_rank,
         (SELECT count(*) FROM school_memberships m JOIN users u ON u.id=m.user_id WHERE m.school_id=s.id AND m.active AND u.active) AS users_count,
         EXISTS (SELECT 1 FROM school_memberships m2 JOIN rbac_assignments a2 ON a2.membership_id=m2.id AND a2.active
                 JOIN rbac_roles r2 ON r2.id=a2.role_id AND r2.code='ADMIN_SYSTEME_ECOLE' WHERE m2.school_id=s.id) AS has_admin,
         EXISTS (SELECT 1 FROM school_memberships m3 JOIN rbac_assignments a3 ON a3.membership_id=m3.id AND a3.active
                 JOIN rbac_roles r3 ON r3.id=a3.role_id AND r3.code='ADMIN_SYSTEME_ECOLE' JOIN users u3 ON u3.id=m3.user_id
                 WHERE m3.school_id=s.id AND m3.active AND u3.active AND NOT coalesce(u3.must_change_password,false)
                   AND NOT EXISTS (SELECT 1 FROM account_tokens t WHERE t.user_id=u3.id AND t.purpose='INVITATION'
                                   AND t.used_at IS NULL AND t.revoked_at IS NULL AND t.expires_at>now())) AS has_active_admin
    FROM schools s
   WHERE {{search}}
), shaped AS (
  SELECT b.*, CASE WHEN NOT b.has_admin THEN 'ADMIN_MISSING' WHEN NOT b.has_active_admin THEN 'ADMIN_PENDING'
                   WHEN st.has_year AND st.has_classes AND st.has_fees THEN 'COMPLETE' ELSE 'INCOMPLETE' END AS config_state
    FROM base b CROSS JOIN LATERAL platform_school_setup(b.id) st
)
"""
_KEY = "edusync_search_key(s.name || ' ' || s.code || ' ' || coalesce(s.contact_name, ''))"
MAX_TERMS = 5


def _search_sql(q: str | None) -> tuple[str, dict]:
    """Every typed word must appear (any order, accents / case / punctuation ignored); served by the trigram index."""
    words = [w for w in re.split(r"[\s\-'’.,;:/]+", q or "") if w][:MAX_TERMS]
    if not words:
        return "TRUE", {}
    return " AND ".join(f"{_KEY} LIKE '%' || edusync_search_key(CAST(:w{i} AS text)) || '%'" for i in range(len(words))), {f"w{i}": w for i, w in enumerate(words)}


_ORDER = {
    "name": ("lower(name) ASC, id ASC", "(lower(name), id) > (CAST(:k1 AS text), CAST(:kid AS uuid))"),
    "created": ("created_at DESC, id DESC", "(created_at, id) < (CAST(:k1 AS timestamptz), CAST(:kid AS uuid))"),
    "status": ("status_rank ASC, lower(name) ASC, id ASC",
               "(status_rank, lower(name), id) > (CAST(:k0 AS int), CAST(:k1 AS text), CAST(:kid AS uuid))"),
}


def encode_cursor(sort: str, row: dict) -> str:
    key = {"name": [None, row["name"].lower()], "created": [None, row["created_at"].isoformat()],
           "status": [int(row["status_rank"]), row["name"].lower()]}[sort] + [str(row["id"])]
    return base64.urlsafe_b64encode(json.dumps({"s": sort, "k": key}, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(sort: str, cursor: str | None) -> dict | None:
    if not cursor:
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        k0, k1, kid = data["k"]
        if data["s"] != sort or not isinstance(k1, str) or not (k0 is None or type(k0) is int):
            raise ValueError
        if sort == "created":
            datetime.fromisoformat(k1)
        return {"k0": k0, "k1": k1, "kid": str(UUID(str(kid)))}
    except Exception as exc:  # noqa: BLE001 — a forged or stale cursor is just refused
        raise ValueError("Curseur de pagination invalide") from exc


def list_schools(c, *, q: str | None, status: str | None, config: str | None, needs_admin: bool, sort: str, cursor: str | None,
                 limit: int) -> dict:
    q = (q or "").strip()[:80] or None
    search, words = _search_sql(q)
    base = _BASE_TEMPLATE.replace("{search}", search + " AND (CAST(:status AS text) IS NULL OR s.status=:status)")
    args = {"status": status, **words}
    where = []
    if config:
        where.append("config_state = :config"); args["config"] = config
    if needs_admin:                                   # dashboard item "écoles actives sans administrateur"
        where.append("status = 'ACTIVE' AND NOT has_admin")
    filt = (" WHERE " + " AND ".join(where)) if where else ""
    total = int(c.execute(text(base + "SELECT count(*) FROM shaped" + filt), args).scalar_one())
    order, after = _ORDER[sort]
    key = decode_cursor(sort, cursor)
    page_where = list(where) + ([after] if key else [])
    sql = base + "SELECT * FROM shaped" + ((" WHERE " + " AND ".join(page_where)) if page_where else "") + f" ORDER BY {order} LIMIT :lim"
    rows = [dict(r) for r in c.execute(text(sql), {**args, **(key or {}), "lim": limit + 1}).mappings()]
    more = len(rows) > limit
    rows = rows[:limit]
    items = [{k: v for k, v in r.items() if k not in ("status_rank",)} | {"contact_phone_display": format_phone(r["contact_phone"])} for r in rows]
    return {"items": items, "total": total, "has_more": more, "next_cursor": encode_cursor(sort, rows[-1]) if more and rows else None,
            "limit": limit, "sort": sort}


def city_suggestions(c, province: str | None) -> list[str]:
    """Chef-lieu of the province + localities already used by schools of that province (never an invented list)."""
    prov = normalize_province(province) if province else None
    used = [r[0] for r in c.execute(text("""SELECT city FROM schools WHERE city IS NOT NULL AND btrim(city)<>''
        AND (CAST(:p AS text) IS NULL OR province=:p) GROUP BY city ORDER BY count(*) DESC, city LIMIT 40"""), {"p": prov})]
    seen, out = set(), []
    for city in ([PROVINCE_CAPITALS[prov]] if prov else []) + used:
        if city.lower() not in seen:
            seen.add(city.lower()); out.append(city)
    return out


# ---------------------------------------------------------------- school sheet
def school_sheet(c, school_id, *, can_audit: bool) -> dict | None:
    s = c.execute(text("""SELECT id,code,name,status,email,phone,address,city,province,contact_name,contact_function,contact_phone,
        contact_email,created_at,updated_at,version FROM schools WHERE id=:id"""), {"id": school_id}).mappings().first()
    if not s:
        return None
    admins = [dict(r) for r in c.execute(text("""SELECT m.id membership_id, u.id user_id, u.full_name, u.email, u.active user_active,
          m.active membership_active, coalesce(u.must_change_password,false) must_change_password,
          EXISTS (SELECT 1 FROM account_tokens t WHERE t.user_id=u.id AND t.purpose='INVITATION' AND t.used_at IS NULL
                  AND t.revoked_at IS NULL AND t.expires_at>now()) invitation_pending,
          (SELECT max(last_seen_at) FROM user_device_sessions d WHERE d.user_id=u.id AND d.school_id=:id) last_seen_at
        FROM school_memberships m JOIN users u ON u.id=m.user_id
        JOIN rbac_assignments a ON a.membership_id=m.id AND a.active JOIN rbac_roles r ON r.id=a.role_id AND r.code=:admin
        WHERE m.school_id=:id ORDER BY m.active DESC, lower(u.full_name)"""), {"id": school_id, "admin": SCHOOL_ADMIN_ROLE}).mappings()]
    for a in admins:
        a["state"] = ("DISABLED" if not (a["user_active"] and a["membership_active"])
                      else "PENDING" if a["must_change_password"] or a["invitation_pending"] else "ACTIVE")
    counts = c.execute(text("""SELECT
        (SELECT count(*) FROM school_memberships m JOIN users u ON u.id=m.user_id WHERE m.school_id=:id AND m.active AND u.active) users_active,
        (SELECT count(*) FROM school_memberships m WHERE m.school_id=:id AND NOT m.active) users_disabled,
        (SELECT count(*) FROM account_tokens t WHERE t.school_id=:id AND t.purpose='INVITATION' AND t.used_at IS NULL
           AND t.revoked_at IS NULL AND t.expires_at>now()) invitations_pending,
        (SELECT max(last_seen_at) FROM user_device_sessions WHERE school_id=:id) last_activity_at,
        (SELECT count(*) FROM sync_conflicts WHERE school_id=:id AND status='OPEN') open_conflicts"""),
        {"id": school_id}).mappings().one()
    setup = c.execute(text("SELECT * FROM platform_school_setup(:id)"), {"id": school_id}).mappings().one()
    active_admins = sum(1 for a in admins if a["state"] == "ACTIVE")
    readiness = {"school_identity": True, "initial_admin": bool(admins), "academic_year": bool(setup["has_year"]),
                 "classes": bool(setup["has_classes"]), "fee_catalog": bool(setup["has_fees"])}
    config = ("ADMIN_MISSING" if not admins else "ADMIN_PENDING" if active_admins == 0
              else "COMPLETE" if all(readiness.values()) else "INCOMPLETE")
    history = None
    if can_audit:
        history = [dict(r) for r in c.execute(text("""SELECT a.id, a.occurred_at, a.action, a.result, a.reason, u.full_name actor
            FROM audit_events a LEFT JOIN users u ON u.id=a.actor_user_id
            WHERE a.school_id=:id AND (a.action LIKE 'SCHOOL\\_%' ESCAPE '\\' OR a.action LIKE 'PLATFORM\\_%' ESCAPE '\\')
            ORDER BY a.occurred_at DESC, a.id DESC LIMIT 25"""), {"id": school_id}).mappings()]
    school = dict(s) | {"phone_display": format_phone(s["phone"]), "contact_phone_display": format_phone(s["contact_phone"])}
    return {
        "school": school, "admins": admins, "readiness": readiness, "ready_count": sum(readiness.values()), "total_gates": len(readiness),
        "config_state": config, "global_lock": False,   # readiness is progressive: a missing gate never locks the school
        "counters": {"users_active": int(counts["users_active"]), "users_disabled": int(counts["users_disabled"]),
                     "admins_active": active_admins, "invitations_pending": int(counts["invitations_pending"])},
        "health": {"access_ok": s["status"] == "ACTIVE" and active_admins > 0, "status": s["status"], "admin_active": active_admins > 0,
                   "configuration": config, "last_activity_at": counts["last_activity_at"], "open_conflicts": int(counts["open_conflicts"])},
        "history": history,
    }


def iso(value):
    return value.isoformat() if isinstance(value, datetime) else value
