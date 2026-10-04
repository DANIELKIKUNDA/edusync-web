from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class AcademicYearStatus(StrEnum):
    PREPARED = "PREPARED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


@dataclass(slots=True)
class AcademicYear:
    school_id: UUID
    code: str
    label: str
    start_date: date
    end_date: date
    id: UUID = field(default_factory=uuid4)
    status: AcademicYearStatus = AcademicYearStatus.PREPARED
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.code = self.code.strip().upper()
        self.label = self.label.strip()
        if not self.code or not self.label:
            raise ValueError("Code et libellé d'année scolaire obligatoires")
        if self.end_date <= self.start_date:
            raise ValueError("La fin de l'année scolaire doit être postérieure au début")

    def activate(self) -> None:
        if self.status != AcademicYearStatus.PREPARED:
            raise ValueError(f"Impossible d'activer une année {self.status}; réouvrez-la d'abord si nécessaire")
        self.status = AcademicYearStatus.ACTIVE

    def close(self) -> None:
        if self.status != AcademicYearStatus.ACTIVE:
            raise ValueError("Seule l'année active peut être clôturée")
        self.status = AcademicYearStatus.CLOSED

    def archive(self) -> None:
        if self.status != AcademicYearStatus.CLOSED:
            raise ValueError("Une année doit être clôturée avant archivage")
        self.status = AcademicYearStatus.ARCHIVED

    def reopen(self) -> None:
        if self.status not in {AcademicYearStatus.CLOSED, AcademicYearStatus.ARCHIVED}:
            raise ValueError("Seule une année clôturée/archivée peut être réouverte")
        self.status = AcademicYearStatus.PREPARED


@dataclass(frozen=True, slots=True)
class ReadinessItem:
    code: str
    label: str
    state: str
    detail: str
    blocking_only_for: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReadinessSnapshot:
    school_id: UUID
    items: tuple[ReadinessItem, ...]

    @property
    def ready_count(self) -> int:
        return sum(1 for x in self.items if x.state == "READY")

    @property
    def percent(self) -> int:
        if not self.items:
            return 100
        return round(self.ready_count * 100 / len(self.items))


def compute_readiness(*, school_id: UUID, has_identity: bool, active_years: int,
                      enabled_sections: int, enabled_classes: int, active_fee_types: int,
                      active_tariffs: int, internal_notifications_enabled: bool,
                      external_sms_enabled: bool) -> ReadinessSnapshot:
    """Progressive readiness. Never returns a global product lock."""
    items = (
        ReadinessItem("IDENTITY", "Identité de l'école", "READY" if has_identity else "TO_COMPLETE",
                      "L'école possède une identité minimale." if has_identity else "Compléter l'identité.", ()),
        ReadinessItem("ACADEMIC_YEAR", "Année scolaire", "READY" if active_years == 1 else "TO_CONFIRM",
                      "Une année est active." if active_years == 1 else "Confirmer/activer l'année avant une inscription.",
                      ("ENROLL_STUDENT", "GENERATE_FEES")),
        ReadinessItem("STRUCTURE", "Sections et classes", "READY" if enabled_sections and enabled_classes else "TO_COMPLETE",
                      "Structure opérationnelle." if enabled_sections and enabled_classes else "Sélectionner les sections et ouvrir les classes réellement organisées.",
                      ("ENROLL_STUDENT",)),
        ReadinessItem("FEE_TYPES", "Types de frais", "READY" if active_fee_types else "TO_COMPLETE",
                      "Types de frais disponibles." if active_fee_types else "Confirmer au moins un type de frais avant tarification.",
                      ("CONFIGURE_TARIFF",)),
        ReadinessItem("TARIFFS", "Tarifs", "READY" if active_tariffs else "TO_COMPLETE",
                      "Des tarifs positifs sont actifs." if active_tariffs else "Saisissez les tarifs réels de l'école pour pouvoir générer les frais.",
                      ("GENERATE_FEES",)),
        ReadinessItem("INTERNAL_NOTIFICATIONS", "Notifications internes", "READY" if internal_notifications_enabled else "TO_CONFIRM",
                      "Notifications internes actives." if internal_notifications_enabled else "Activer si l'école souhaite les alertes internes.", ()),
        ReadinessItem("EXTERNAL_SMS", "SMS externes", "READY" if external_sms_enabled else "NOT_APPLICABLE",
                      "Canal SMS activé." if external_sms_enabled else "Désactivé tant qu'aucun fournisseur SMS n'est configuré.",
                      ("SEND_SMS",)),
    )
    return ReadinessSnapshot(school_id=school_id, items=items)


POLICY_DEFAULTS: dict[str, dict[str, Any]] = {
    "PAYMENT": {"allow_partial_payments": True, "currencies": ["CDF", "USD"], "implicit_currency_conversion": False},
    "DOCUMENTS": {"receipt_numbering": "SERVER_SEQUENCE", "document_history": True},
    "BACKUP": {"enabled": True, "offsite_required": True},
    "COMMUNICATIONS": {"internal_notifications": True, "external_sms_enabled": False},
}
