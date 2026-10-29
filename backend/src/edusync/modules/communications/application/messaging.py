"""Use-case side of external messaging: audience resolution, SMS cost preview, credit reservation and the
transactional-outbox request. Everything here runs INSIDE the caller's business transaction; nothing calls a
provider. The communications worker reads the outbox event after commit, applies the NotificationPolicy and sends.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import text

from edusync.modules.communications.domain.models import sms_segments

MAX_SMS_CHARS = 400            # Orange bills up to 400 characters (3 units); longer texts are refused before sending
CHANNELS = ("SMS", "EMAIL", "PUSH")


def e164(phone: str | None) -> str | None:
    """Strict E.164 (+ and 8 to 15 digits) or None. Normalisation is done at data entry (schooling.normalized_phone)."""
    if not phone:
        return None
    p = phone.strip().replace(" ", "")
    return p if p.startswith("+") and p[1:].isdigit() and 8 <= len(p) - 1 <= 15 else None


def sms_units(body: str) -> int:
    """Billable units of one SMS: the larger of the GSM/Unicode segment count and Orange's documented character
    bands (1-160 -> 1, 161-320 -> 2, 321-400 -> 3). Reserved before sending, consumed when the provider accepts."""
    n = len(body or "")
    bands = 1 if n <= 160 else 2 if n <= 320 else 3
    return max(sms_segments(body or ""), bands)


@dataclass(frozen=True)
class Recipient:
    kind: str                      # GUARDIAN | USER
    ref: UUID
    display_name: str | None = None
    phone: str | None = None
    email: str | None = None
    user_id: UUID | None = None
    target_school_id: UUID | None = None   # platform message to a school user: push to that school's devices only


# ---------------------------------------------------------------------------------------------- audience
def _scope_ok(actor, cap: str | None, section_code: str | None) -> bool:
    """Section-scoped roles only reach their sections (scope value = section code, e.g. SECONDAIRE); a capability
    granted without scope rows is school-wide."""
    if cap is None or getattr(actor, "is_platform_admin", False):
        return True
    scopes = actor.scopes_for(cap)
    return not scopes or actor.scope_allows(cap, "SECTION", (section_code or "").upper() or None)


def resolve_audience(conn, actor, school_id: UUID, audience_type: str, audience_ref: UUID | None, cap: str | None) -> list[Recipient]:
    """Primary guardian of each family of the students in scope (active students, validated enrollment of the
    active academic year). One recipient per guardian: a parent with several children is counted once."""
    audience_type = audience_type.upper()
    where, params = [], {"sid": str(school_id)}
    if audience_type == "INDIVIDUAL":
        if not audience_ref:
            raise ValueError("Choisissez l'élève destinataire")
        where.append("s.id=:ref")
    elif audience_type == "CLASS":
        if not audience_ref:
            raise ValueError("Choisissez la classe")
        where.append("e.class_id=:ref")
    elif audience_type == "SECTION":
        if not audience_ref:
            raise ValueError("Choisissez la section")
        where.append("c.section_id=:ref")
    elif audience_type != "SCHOOL":
        raise ValueError("Audience inconnue")
    if audience_ref:
        params["ref"] = str(audience_ref)
    rows = conn.execute(text(f"""
        SELECT g.id, g.full_name, coalesce(g.normalized_phone, g.phone) AS phone, g.email, sec.code AS section_code
        FROM students s
        JOIN enrollments e ON e.student_id=s.id AND e.school_id=s.school_id AND e.status='VALIDATED'
        JOIN academic_years y ON y.id=e.academic_year_id AND y.status='ACTIVE'
        JOIN school_classes c ON c.id=e.class_id AND c.school_id=e.school_id
        JOIN school_sections sec ON sec.id=c.section_id
        JOIN family_guardians fg ON fg.family_id=s.family_id AND fg.school_id=s.school_id AND fg.is_primary AND fg.active
        JOIN guardians g ON g.id=fg.guardian_id
        WHERE s.school_id=:sid AND s.status='ACTIVE' {('AND ' + ' AND '.join(where)) if where else ''}
        ORDER BY g.id, sec.code"""), params).mappings().all()
    out, seen = [], set()
    for r in rows:
        if not _scope_ok(actor, cap, r["section_code"]):
            continue
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        out.append(Recipient("GUARDIAN", r["id"], r["full_name"], r["phone"], r["email"]))
    return out


def preview(conn, school_id: UUID, recipients: list[Recipient], channels: list[str], body: str) -> dict:
    """What will happen before confirmation: valid / invalid destinations, duplicates removed, SMS units and the
    wallet balance after sending. The same figures are recomputed at confirmation (never trusted from the client)."""
    phones, invalid, dupes, sms_targets = set(), 0, 0, []
    for r in recipients:
        p = e164(r.phone)
        if not p:
            invalid += 1
        elif p in phones:
            dupes += 1
        else:
            phones.add(p)
            sms_targets.append(r)
    units_each = sms_units(body) if "SMS" in channels else 0
    units = units_each * len(sms_targets) if "SMS" in channels else 0
    wallet = conn.execute(text("SELECT balance, reserved FROM school_sms_wallets WHERE school_id=:s"), {"s": str(school_id)}).mappings().first()
    balance, reserved = (wallet["balance"], wallet["reserved"]) if wallet else (0, 0)
    available = balance - reserved
    emails = {(r.email or "").strip().lower() for r in recipients if r.email and "@" in r.email}
    return {"recipients": len(recipients), "sms_valid": len(sms_targets), "sms_invalid": invalid, "sms_duplicates_removed": dupes,
            "email_valid": len(emails), "characters": len(body), "units_per_sms": units_each, "sms_units": units,
            "wallet_balance": balance, "wallet_reserved": reserved, "wallet_available": available,
            "balance_after": available - units, "sufficient": available >= units, "too_long": len(body) > MAX_SMS_CHARS and "SMS" in channels,
            "fingerprint": fingerprint(recipients, channels, body)}


def fingerprint(recipients: list[Recipient], channels: list[str], body: str) -> str:
    """Binds a confirmation to what was previewed: a change of audience, channel or text requires a new preview."""
    h = hashlib.sha256()
    h.update(json.dumps(sorted(channels)).encode())
    h.update(body.encode("utf-8"))
    for r in sorted(recipients, key=lambda x: str(x.ref)):
        h.update(f"{r.kind}:{r.ref}:{r.phone}:{r.email}".encode())
    return h.hexdigest()[:32]


# ---------------------------------------------------------------------------------------------- request (outbox)
def request_message(conn, *, school_id: UUID | None, kind: str, channels: list[str], body: str, recipients: list[Recipient],
                    idempotency_key: str, created_by: UUID | None, subject: str | None = None, audience_type: str = "INDIVIDUAL",
                    audience_ref: UUID | None = None, template_code: str | None = None, link_path: str | None = None,
                    secret_by_ref: dict[UUID, str] | None = None, sealer=None, reserve_sms: bool = True) -> dict:
    """Records the message, its recipients, the SMS credit reservation and the COMMUNICATION_REQUESTED outbox event in
    the caller's transaction. Idempotent on (school, idempotency key): a replay returns the first message unchanged."""
    channels = [c for c in dict.fromkeys(ch.upper() for ch in channels) if c in CHANNELS]
    if not channels:
        raise ValueError("Aucun canal externe demandé")
    existing = conn.execute(text("""SELECT id, sms_segments_reserved, recipient_count FROM communication_messages
        WHERE idempotency_key=:k AND school_id IS NOT DISTINCT FROM :s"""), {"k": idempotency_key, "s": str(school_id) if school_id else None}).mappings().first()
    if existing:
        return {"id": str(existing["id"]), "replayed": True, "sms_units_reserved": existing["sms_segments_reserved"],
                "recipients": existing["recipient_count"]}
    mid = uuid4()
    units = 0
    if "SMS" in channels:
        if school_id is None:
            raise ValueError("Les SMS sont toujours rattachés à une école")
        if len(body) > MAX_SMS_CHARS:
            raise ValueError(f"SMS limité à {MAX_SMS_CHARS} caractères")
        seen, sms_count = set(), 0
        for r in recipients:
            p = e164(r.phone)
            if p and p not in seen:
                seen.add(p)
                sms_count += 1
        units = sms_units(body) * sms_count
    conn.execute(text("""INSERT INTO communication_messages(id, school_id, kind, audience_type, audience_ref, subject, body, created_by,
            idempotency_key, channels, template_code, link_path, recipient_count, sms_segments_reserved)
        VALUES (:id, :s, :kind, :aud, :ref, :sub, :body, :by, :key, :ch, :tpl, :link, :n, :units)"""),
        {"id": str(mid), "s": str(school_id) if school_id else None, "kind": kind, "aud": audience_type.upper(),
         "ref": str(audience_ref) if audience_ref else None, "sub": subject, "body": body, "by": str(created_by) if created_by else None,
         "key": idempotency_key, "ch": channels, "tpl": template_code, "link": link_path, "n": len(recipients), "units": units})
    if secret_by_ref and sealer is None:
        raise ValueError("Un secret à usage unique doit être chiffré (sealer obligatoire)")
    for r in recipients:
        rid = uuid4()
        sealed = sealer(str(rid), secret_by_ref[r.ref]) if secret_by_ref and r.ref in secret_by_ref else None
        conn.execute(text("""INSERT INTO communication_recipients(id, school_id, message_id, recipient_kind, recipient_ref, user_id,
                phone_e164, email, display_name, secret_ciphertext, target_school_id)
            VALUES (:id, :s, :m, :k, :ref, :u, :p, :e, :n, :sec, :ts) ON CONFLICT (message_id, recipient_kind, recipient_ref) DO NOTHING"""),
            {"id": str(rid), "s": str(school_id) if school_id else None, "m": str(mid), "k": r.kind, "ref": str(r.ref),
             "u": str(r.user_id) if r.user_id else None, "p": e164(r.phone), "e": (r.email or "").strip().lower() or None,
             "n": r.display_name, "sec": sealed, "ts": str(r.target_school_id) if r.target_school_id else None})
    if units and reserve_sms:
        # Raises SMS_INSUFFICIENT_CREDIT (no negative balance); the whole request is then rolled back.
        from edusync.modules.communications.application.wallet import wallet_apply
        wallet_apply(conn, school_id=school_id, movement="RESERVATION", quantity=units, key=f"reserve:{mid}", actor=created_by,
                     source_type="communication_message", source_id=mid)
    conn.execute(text("""INSERT INTO outbox_events(school_id, event_type, aggregate_type, aggregate_id, payload, deduplication_key)
        VALUES (:s, 'COMMUNICATION_REQUESTED', 'communication_message', :m, CAST(:p AS jsonb), :d)"""),
        {"s": str(school_id) if school_id else None, "m": str(mid), "d": f"communication:{mid}",
         "p": json.dumps({"message_id": str(mid), "channels": channels})})
    return {"id": str(mid), "replayed": False, "sms_units_reserved": units, "recipients": len(recipients)}
