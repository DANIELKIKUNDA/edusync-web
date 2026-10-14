from __future__ import annotations

from decimal import Decimal

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import StrEnum
import re
import unicodedata
from uuid import UUID, uuid4


class StudentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    ABANDON = "ABANDON"
    TRANSFERRED = "TRANSFERRED"
    SUSPENDED = "SUSPENDED"
    INACTIVE = "INACTIVE"


class EnrollmentStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class GuardianRole(StrEnum):
    PERE = "PERE"
    MERE = "MERE"
    TUTEUR = "TUTEUR"
    AUTRE = "AUTRE"


class ResolutionConfidence(StrEnum):
    CERTAIN = "CERTAIN"
    POSSIBLE = "POSSIBLE"
    NONE = "NONE"


class FamilyLabelOrigin(StrEnum):
    PRIMARY_GUARDIAN = "PRIMARY_GUARDIAN"
    STUDENT = "STUDENT"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class ContactStatus(StrEnum):
    COMPLETE = "COMPLETE"
    TO_COMPLETE = "TO_COMPLETE"


class BenefitKind(StrEnum):
    LARGE_FAMILY = "LARGE_FAMILY"
    STAFF_CHILD = "STAFF_CHILD"
    SCHOOL_SUPPORT = "SCHOOL_SUPPORT"
    THIRD_PARTY = "THIRD_PARTY"
    OTHER = "OTHER"


def clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = " ".join(value.strip().split())
    return value or None


def normalized_phone(value: str | None) -> str | None:
    """Normalize only for lookup; never use as an automatic household merge key."""
    if not value:
        return None
    digits = re.sub(r"\D", "", value)
    if not digits:
        return None
    if digits.startswith("243"):
        return "+" + digits
    if digits.startswith("0") and len(digits) >= 9:
        return "+243" + digits[1:]
    return "+" + digits


def search_token(value: str | None) -> str:
    if not value:
        return ""
    n = unicodedata.normalize("NFKD", value)
    return " ".join("".join(c for c in n if not unicodedata.combining(c)).lower().split())


def generate_family_label(*, guardian_name: str | None = None, student_name: str | None = None) -> tuple[str, FamilyLabelOrigin]:
    guardian = clean_name(guardian_name)
    student = clean_name(student_name)
    if guardian:
        return f"Foyer de {guardian}", FamilyLabelOrigin.PRIMARY_GUARDIAN
    if student:
        return f"Foyer {student}", FamilyLabelOrigin.STUDENT
    return "Foyer à compléter", FamilyLabelOrigin.STUDENT


@dataclass(slots=True)
class Family:
    school_id: UUID
    code: str
    display_name: str
    id: UUID = field(default_factory=uuid4)
    display_name_origin: FamilyLabelOrigin = FamilyLabelOrigin.STUDENT
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    contact_status: ContactStatus = ContactStatus.TO_COMPLETE
    notes: str | None = None
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.code = self.code.strip().upper()
        self.display_name = " ".join(self.display_name.strip().split())
        self.phone = normalized_phone(self.phone)
        if not self.code or not self.display_name:
            raise ValueError("Code et libellé de foyer obligatoires")


@dataclass(slots=True)
class Guardian:
    school_id: UUID
    full_name: str
    id: UUID = field(default_factory=uuid4)
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    occupation: str | None = None
    notes: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        self.full_name = " ".join(self.full_name.strip().split())
        if not self.full_name:
            raise ValueError("Nom du responsable obligatoire")
        self.phone = normalized_phone(self.phone)


@dataclass(slots=True)
class FamilyGuardian:
    school_id: UUID
    family_id: UUID
    guardian_id: UUID
    role: GuardianRole = GuardianRole.TUTEUR
    id: UUID = field(default_factory=uuid4)
    is_primary: bool = False
    active: bool = True
    version: int = 1


@dataclass(slots=True)
class Student:
    school_id: UUID
    family_id: UUID
    matricule: str
    last_name: str
    middle_name: str
    first_name: str
    id: UUID = field(default_factory=uuid4)
    gender: str | None = None
    birth_date: date | None = None
    birth_place: str | None = None
    nationality: str | None = None
    address: str | None = None
    previous_school: str | None = None
    photo_url: str | None = None
    status: StudentStatus = StudentStatus.ACTIVE
    profile_completeness: int = 0
    notes: str | None = None
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.matricule = self.matricule.strip().upper()
        self.last_name = clean_name(self.last_name) or ""
        self.middle_name = clean_name(self.middle_name) or ""
        self.first_name = clean_name(self.first_name) or ""
        if not all((self.matricule, self.last_name, self.middle_name, self.first_name)):
            raise ValueError("Nom, postnom, prénom et matricule sont obligatoires")
        if self.gender not in {"M", "F"}:
            raise ValueError("Sexe obligatoire : M ou F")
        self.profile_completeness = self.compute_completeness()

    @property
    def display_name(self) -> str:
        return " ".join(x for x in (self.last_name, self.middle_name, self.first_name) if x)

    def compute_completeness(self) -> int:
        # Enrollment-critical identity includes sex; birth and other fields may be completed later.
        fields = [self.last_name, self.middle_name, self.first_name, self.family_id,
                  self.gender, self.birth_date, self.birth_place, self.nationality,
                  self.address, self.previous_school]
        present = sum(1 for x in fields if x not in (None, ""))
        return round(present * 100 / len(fields))


@dataclass(slots=True)
class Enrollment:
    school_id: UUID
    student_id: UUID
    academic_year_id: UUID
    class_id: UUID
    id: UUID = field(default_factory=uuid4)
    status: EnrollmentStatus = EnrollmentStatus.VALIDATED
    enrolled_on: date = field(default_factory=date.today)
    enrollment_kind: str = "NEW"
    origin_school: str | None = None
    notes: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if self.enrollment_kind not in {"NEW", "REENROLLMENT", "TRANSFER_IN"}:
            raise ValueError("Type d'inscription invalide")


@dataclass(slots=True)
class StudentStatusEvent:
    school_id: UUID
    student_id: UUID
    event_type: str
    effective_date: date
    reason: str
    id: UUID = field(default_factory=uuid4)
    destination: str | None = None
    actor_user_id: UUID | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.reason = self.reason.strip()
        if self.event_type not in {"ABANDON", "TRANSFER", "SUSPEND", "REINTEGRATE", "CLASS_CHANGE"}:
            raise ValueError("Événement scolaire invalide")
        if not self.reason:
            raise ValueError("Le motif est obligatoire")
        if self.event_type == "TRANSFER" and not clean_name(self.destination):
            raise ValueError("La destination du transfert est obligatoire")


@dataclass(slots=True)
class StudentBenefit:
    school_id: UUID
    student_id: UUID
    academic_year_id: UUID
    kind: BenefitKind
    id: UUID = field(default_factory=uuid4)
    source_reference: str | None = None
    selected_explicitly: bool = True
    active: bool = True
    notes: str | None = None
    version: int = 1
    # Desktop student_benefits.configured_percent / applies_to_fee_code: frozen from the policy at selection time.
    configured_percent: Decimal = Decimal("0")
    applies_to_fee_code: str | None = None

    def __post_init__(self) -> None:
        if not self.selected_explicitly:
            raise ValueError("Un avantage élève doit être attribué explicitement")


@dataclass(frozen=True, slots=True)
class SchoolingSummary:
    total_students: int
    active_students: int
    new_enrollments: int
    reenrollments: int
    families: int
    families_to_complete: int
    guardians: int
    large_family_candidates: int
    staff_children: int
    abandoned: int
    transferred: int
