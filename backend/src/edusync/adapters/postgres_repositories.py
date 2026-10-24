from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from edusync.modules.audit.domain.audit import AuditRecord
from edusync.modules.iam.domain.models import Membership, User
from edusync.modules.platform.domain.school import School, SchoolStatus
from edusync.modules.sync.domain.outbox import OutboxMessage
from edusync.shared.domain.concurrency import OptimisticConcurrencyError


def _json(value):
    return json.dumps(value, ensure_ascii=False, default=str) if value is not None else None


@dataclass(slots=True)
class PostgresSchoolRepository:
    connection: Connection

    @staticmethod
    def _school(row) -> School:
        m = row._mapping
        return School(
            id=m["id"], name=m["name"], code=m["code"], status=SchoolStatus(m["status"]),
            logo_url=m["logo_url"], email=m["email"], phone=m["phone"],
            address=m.get("address"), city=m.get("city"), province=m.get("province"),
            contact_name=m.get("contact_name"), contact_function=m.get("contact_function"),
            contact_phone=m.get("contact_phone"), contact_email=m.get("contact_email"),
            created_at=m["created_at"], updated_at=m["updated_at"], version=int(m["version"]),
        )

    def add(self, school: School) -> None:
        self.connection.execute(text("""
            INSERT INTO schools(id,code,name,status,logo_url,email,phone,address,city,province,
                                contact_name,contact_function,contact_phone,contact_email,created_at,updated_at,version)
            VALUES (:id,:code,:name,:status,:logo_url,:email,:phone,:address,:city,:province,
                    :contact_name,:contact_function,:contact_phone,:contact_email,:created_at,:updated_at,:version)
        """), {
            "id": school.id, "code": school.code, "name": school.name, "status": school.status.value,
            "logo_url": school.logo_url, "email": school.email, "phone": school.phone,
            "address": school.address, "city": school.city, "province": school.province,
            "contact_name": school.contact_name, "contact_function": school.contact_function,
            "contact_phone": school.contact_phone, "contact_email": school.contact_email,
            "created_at": school.created_at, "updated_at": school.updated_at, "version": school.version,
        })

    def get(self, school_id: UUID) -> School | None:
        row = self.connection.execute(text("""
            SELECT id,code,name,status,logo_url,email,phone,address,city,province,contact_name,contact_function,contact_phone,contact_email,created_at,updated_at,version
              FROM schools WHERE id=:id
        """), {"id": school_id}).first()
        return None if row is None else self._school(row)

    def get_by_code(self, code: str) -> School | None:
        row = self.connection.execute(text("""
            SELECT id,code,name,status,logo_url,email,phone,address,city,province,created_at,updated_at,version
              FROM schools WHERE code=:code
        """), {"code": code.strip().upper()}).first()
        return None if row is None else self._school(row)

    def list(self) -> list[School]:
        rows = self.connection.execute(text("""
            SELECT id,code,name,status,logo_url,email,phone,address,city,province,created_at,updated_at,version
              FROM schools ORDER BY lower(name), code
        """)).all()
        return [self._school(r) for r in rows]

    def save(self, school: School) -> None:
        expected = school.version
        row = self.connection.execute(text("""
            UPDATE schools
               SET name=:name, code=:code, status=:status, logo_url=:logo_url,
                   email=:email, phone=:phone, address=:address, city=:city, province=:province, updated_at=:updated_at, version=version+1
             WHERE id=:id AND version=:expected
             RETURNING version
        """), {
            "id": school.id, "name": school.name, "code": school.code, "status": school.status.value,
            "logo_url": school.logo_url, "email": school.email, "phone": school.phone,
            "address": school.address, "city": school.city, "province": school.province,
            "updated_at": school.updated_at, "expected": expected,
        }).first()
        if row is None:
            raise OptimisticConcurrencyError(
                f"École {school.id} modifiée par une autre session (version attendue {expected})"
            )
        school.version = int(row[0])

    def save_identity(self, school: School) -> None:
        """A school updates its own identity only (name, contacts, address, logo): never its code or status, which belong
        to the platform. The tenant role holds UPDATE on exactly these columns (migration 0086)."""
        expected = school.version
        row = self.connection.execute(text("""
            UPDATE schools
               SET name=:name, logo_url=:logo_url, email=:email, phone=:phone, address=:address, city=:city, province=:province,
                   updated_at=now(), version=version+1
             WHERE id=:id AND version=:expected
             RETURNING version, updated_at
        """), {
            "id": school.id, "name": school.name, "logo_url": school.logo_url, "email": school.email, "phone": school.phone,
            "address": school.address, "city": school.city, "province": school.province, "expected": expected,
        }).first()
        if row is None:
            raise OptimisticConcurrencyError(
                f"École {school.id} modifiée par une autre session (version attendue {expected})"
            )
        school.version, school.updated_at = int(row[0]), row[1]


@dataclass(slots=True)
class PostgresUserRepository:
    connection: Connection

    @staticmethod
    def _user(row) -> User:
        m = row._mapping
        return User(
            id=m["id"], email=m["email"], full_name=m["full_name"], password_hash=m["password_hash"],
            active=bool(m["active"]), is_platform_admin=bool(m["is_platform_admin"]),
            created_at=m["created_at"], version=int(m["version"]),
        )

    def add(self, user: User) -> None:
        self.connection.execute(text("""
            INSERT INTO users(id,email,full_name,password_hash,active,is_platform_admin,created_at,version)
            VALUES (:id,:email,:full_name,:password_hash,:active,:platform,:created_at,:version)
        """), {"id": user.id, "email": user.email, "full_name": user.full_name,
                 "password_hash": user.password_hash, "active": user.active,
                 "platform": user.is_platform_admin, "created_at": user.created_at, "version": user.version})

    def require_password_change(self, user_id: UUID, *, set_by: str) -> None:
        # The password was chosen by someone else (platform bootstrap): it only opens the "choose your password" step.
        self.connection.execute(text("UPDATE users SET must_change_password=true,password_set_by=:by WHERE id=:id"),
                                {"id": user_id, "by": set_by})

    def get(self, user_id: UUID) -> User | None:
        row = self.connection.execute(text("""
            SELECT id,email,full_name,password_hash,active,is_platform_admin,created_at,version
              FROM users WHERE id=:id
        """), {"id": user_id}).first()
        return None if row is None else self._user(row)

    def get_by_email(self, email: str) -> User | None:
        row = self.connection.execute(text("""
            SELECT id,email,full_name,password_hash,active,is_platform_admin,created_at,version
              FROM users WHERE email=:email
        """), {"email": email.strip().lower()}).first()
        return None if row is None else self._user(row)


@dataclass(slots=True)
class PostgresMembershipRepository:
    connection: Connection

    @staticmethod
    def _membership(row) -> Membership:
        m = row._mapping
        return Membership(id=m["id"], user_id=m["user_id"], school_id=m["school_id"],
                          active=bool(m["active"]), created_at=m["created_at"], version=int(m["version"]))

    def add(self, membership: Membership) -> None:
        self.connection.execute(text("""
            INSERT INTO school_memberships(id,school_id,user_id,active,created_at,version)
            VALUES (:id,:school_id,:user_id,:active,:created_at,:version)
        """), {"id": membership.id, "school_id": membership.school_id, "user_id": membership.user_id,
                 "active": membership.active, "created_at": membership.created_at, "version": membership.version})

    def get_for_user_school(self, user_id: UUID, school_id: UUID) -> Membership | None:
        row = self.connection.execute(text("""
            SELECT id,school_id,user_id,active,created_at,version
              FROM school_memberships WHERE user_id=:uid AND school_id=:sid
        """), {"uid": user_id, "sid": school_id}).first()
        return None if row is None else self._membership(row)

    def get(self, membership_id: UUID) -> Membership | None:
        row = self.connection.execute(text("""
            SELECT id,school_id,user_id,active,created_at,version
              FROM school_memberships WHERE id=:id
        """), {"id": membership_id}).first()
        return None if row is None else self._membership(row)

    def set_role(self, membership_id: UUID, role_code: str) -> None:
        """Assign an ACTIVE industrial RBAC role at SCHOOL scope.

        Point 4 retires the legacy roles/role_permissions write path. Standard and
        custom roles are now resolved through rbac_roles + rbac_assignments.
        """
        membership = self.get(membership_id)
        if membership is None:
            raise LookupError("Appartenance école introuvable")
        role = self.connection.execute(text("""
            SELECT id, level, kind, status
              FROM rbac_roles
             WHERE code=:code
               AND status='ACTIVE'
               AND (kind='SCHOOL_STANDARD' OR (kind='SCHOOL_CUSTOM' AND school_id=:sid))
             ORDER BY CASE WHEN kind='SCHOOL_CUSTOM' THEN 0 ELSE 1 END
             LIMIT 1
        """), {"code": role_code.strip().upper(), "sid": membership.school_id}).first()
        if role is None:
            raise LookupError(f"Rôle RBAC actif inconnu: {role_code}")
        if str(role._mapping["level"]) != "SCHOOL":
            raise ValueError("Un rôle plateforme ne peut pas être affecté à une appartenance école")
        existing = self.connection.execute(text("""
            SELECT id FROM rbac_assignments
             WHERE membership_id=:mid AND role_id=:rid AND active=true
               AND valid_from<=now() AND (valid_until IS NULL OR valid_until>now())
             LIMIT 1
        """), {"mid": membership_id, "rid": role._mapping["id"]}).first()
        if existing is not None:
            return
        assignment = self.connection.execute(text("""
            INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,active,reason)
            VALUES (:uid,:rid,:sid,:mid,true,'BOOTSTRAP_OR_EXPLICIT_ASSIGNMENT')
            RETURNING id
        """), {"uid": membership.user_id, "rid": role._mapping["id"],
                 "sid": membership.school_id, "mid": membership_id}).first()
        self.connection.execute(text("""
            INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value)
            VALUES (:aid,'SCHOOL',NULL)
        """), {"aid": assignment._mapping["id"]})

    def permissions(self, membership_id: UUID) -> frozenset[str]:
        """Return the union of currently effective capabilities for login/UI hints.

        Resource-scope authorization still belongs to PostgresAuthorizationRepository;
        this union is intentionally only a coarse capability list for menu rendering.
        """
        from edusync.adapters.rbac_effective import ALIAS_EXPANSION, ASSIGNMENT_CAPABILITIES
        rows = self.connection.execute(text(f"""
            WITH held(code) AS (
                SELECT ac.capability_code
                  FROM rbac_assignments a
                  JOIN rbac_roles r ON r.id=a.role_id AND r.status='ACTIVE'
                  CROSS JOIN LATERAL ({ASSIGNMENT_CAPABILITIES}) ac
                 WHERE a.membership_id=:mid AND a.active=true
                   AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())
                UNION
                SELECT eg.capability_code
                  FROM rbac_exception_grants eg
                 WHERE eg.membership_id=:mid AND eg.active=true
                   AND eg.valid_from<=now() AND eg.valid_until>now()
            ){ALIAS_EXPANSION}
             ORDER BY 1
        """), {"mid": membership_id}).all()
        return frozenset(str(r[0]) for r in rows)


@dataclass(slots=True)
class PostgresAuditRepository:
    connection: Connection

    def append(self, record: AuditRecord) -> None:
        self.connection.execute(text("""
            INSERT INTO audit_events(
              id,occurred_at,school_id,actor_user_id,membership_id,action,entity_type,entity_id,
              source,result,old_json,new_json,reason,device_id,correlation_id,causation_id,idempotency_key
            ) VALUES (
              :id,:occurred_at,:school_id,:actor_user_id,:membership_id,:action,:entity_type,:entity_id,
              :source,:result,CAST(:old_json AS jsonb),CAST(:new_json AS jsonb),:reason,:device_id,
              :correlation_id,:causation_id,:idempotency_key
            )
        """), {
            "id": record.id, "occurred_at": record.occurred_at, "school_id": record.school_id,
            "actor_user_id": record.actor_user_id, "membership_id": record.membership_id,
            "action": record.action, "entity_type": record.entity_type, "entity_id": record.entity_id,
            "source": record.source, "result": record.result, "old_json": _json(record.old_data),
            "new_json": _json(record.new_data), "reason": record.reason, "device_id": record.device_id,
            "correlation_id": record.correlation_id, "causation_id": record.causation_id,
            "idempotency_key": record.idempotency_key,
        })


@dataclass(slots=True)
class PostgresOutboxRepository:
    connection: Connection

    def add(self, message: OutboxMessage) -> None:
        self.connection.execute(text("""
            INSERT INTO outbox_events(
              id,school_id,event_type,aggregate_type,aggregate_id,payload,correlation_id,causation_id,
              created_at,deduplication_key
            ) VALUES (
              :id,:school_id,:event_type,:aggregate_type,:aggregate_id,CAST(:payload AS jsonb),
              :correlation_id,:causation_id,:created_at,:dedup
            )
            ON CONFLICT DO NOTHING
        """), {
            "id": message.id, "school_id": message.school_id, "event_type": message.event_type,
            "aggregate_type": message.aggregate_type, "aggregate_id": message.aggregate_id,
            "payload": _json(message.payload), "correlation_id": message.correlation_id,
            "causation_id": message.causation_id, "created_at": message.created_at,
            "dedup": message.deduplication_key,
        })
