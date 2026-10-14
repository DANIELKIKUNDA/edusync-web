from __future__ import annotations

from decimal import Decimal

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from edusync.modules.schooling.domain.models import (
    BenefitKind, ContactStatus, Enrollment, Family, Guardian, GuardianRole,
    Student, StudentBenefit, generate_family_label,
)
from edusync.adapters.postgres_schooling import PostgresSchoolingRepository


@dataclass(frozen=True, slots=True)
class EnrollmentPolicy:
    """Terrain-first defaults. Non-critical identity fields can be completed later."""
    required_student_fields: tuple[str, ...] = ("last_name", "middle_name", "first_name", "gender", "class_id")
    guardian_required_at_enrollment: bool = False
    guardian_phone_required: bool = False


class SchoolingService:
    def __init__(self, repo: PostgresSchoolingRepository, *, school_id: UUID, actor_user_id: UUID, permitted_scopes: tuple[tuple[str, str | None], ...] = (("SCHOOL", None),)):
        self.repo = repo
        self.school_id = school_id
        self.actor_user_id = actor_user_id
        self.permitted_scopes = permitted_scopes

    def _class_allowed(self, cls: dict[str, Any]) -> bool:
        if any(t == "SCHOOL" for t, _ in self.permitted_scopes):
            return True
        section = str(cls.get("section_code") or "").upper()
        code = str(cls.get("code") or "").upper()
        return any((t == "SECTION" and str(v or "").upper() == section) or (t == "CLASS" and str(v or "").upper() == code) for t, v in self.permitted_scopes)

    def resolve_household(self, query: str) -> list[dict[str, Any]]:
        return self.repo.resolve_households(self.school_id, query)

    def enroll_family_batch(
        self,
        *,
        children: list[dict[str, Any]],
        family_id: UUID | None = None,
        primary_guardian: dict[str, Any] | None = None,
        additional_guardians: list[dict[str, Any]] | None = None,
        household_query: str | None = None,
        household_confidence: str = "NONE",
        admission_notes: str | None = None,
    ) -> dict[str, Any]:
        if not children:
            raise ValueError("Au moins un enfant doit être inscrit")
        year = self.repo.active_year(self.school_id)
        if not year:
            raise ValueError("Aucune année scolaire ACTIVE. Activez l’année avant l’inscription.")
        policy = self.repo.enrollment_policy(self.school_id)
        allowed_required={"last_name","middle_name","first_name","class_id","gender","birth_date","birth_place","nationality","address","previous_school"}
        required=tuple(x for x in policy.get("required_student_fields",()) if x in allowed_required)
        # The five terrain fields (identity + sex + class) are irreducible; a school may require more, never fewer.
        required=tuple(dict.fromkeys(("last_name","middle_name","first_name","gender","class_id",*required)))
        if policy.get("guardian_required_at_enrollment") and not primary_guardian and not family_id:
            raise ValueError("Un responsable est obligatoire selon la politique d'inscription de l'école")
        if policy.get("guardian_phone_required") and primary_guardian and not str(primary_guardian.get("phone") or "").strip():
            raise ValueError("Le téléphone du responsable est obligatoire selon la politique de l'école")

        # Desktop benefit rules (app/db/schooling.py, enroll family): no cumulation, policy enabled, beneficiary limits.
        large_selected = sum(1 for c in children if c.get("large_family_beneficiary"))
        staff_selected: dict[str, int] = {}
        for c in children:
            if c.get("large_family_beneficiary") and c.get("staff_beneficiary"):
                raise ValueError("Un même élève ne peut pas cumuler deux réductions financières sans politique explicite")
            if c.get("staff_beneficiary"):
                if not c.get("staff_member_id"):
                    raise ValueError("Choisissez l’agent dont l’enfant est bénéficiaire")
                staff_selected[str(c["staff_member_id"])] = staff_selected.get(str(c["staff_member_id"]), 0) + 1
        large_policy = self.repo.benefit_policy(self.school_id, UUID(str(year["id"])), "LARGE_FAMILY")
        staff_policy = self.repo.benefit_policy(self.school_id, UUID(str(year["id"])), "STAFF_CHILD") if staff_selected else None
        if large_selected:
            if large_policy is None:
                raise ValueError("La politique Famille nombreuse n'est pas activée")
            limit = int(large_policy.get("free_beneficiaries") or large_policy.get("max_beneficiaries") or 0)
            existing_large = self.repo.count_benefits(self.school_id, UUID(str(year["id"])), "LARGE_FAMILY", family_id=family_id) if family_id else 0
            if limit > 0 and existing_large + large_selected > limit:
                raise ValueError(f"Cette famille ne peut avoir que {limit} bénéficiaire(s) Famille nombreuse pour cette année")
        if staff_selected:
            if staff_policy is None:
                raise ValueError("La politique Enfants du personnel n'est pas activée")
            limit = int(staff_policy.get("max_beneficiaries") or staff_policy.get("free_beneficiaries") or 0)
            if limit > 0:
                for staff, n in staff_selected.items():
                    if self.repo.count_benefits(self.school_id, UUID(str(year["id"])), "STAFF_CHILD", staff_id=UUID(staff)) + n > limit:
                        raise ValueError(f"Cet agent ne peut avoir que {limit} enfant(s) bénéficiaire(s) pour cette année")

        # Validate the whole batch before writing. This preserves Desktop all-or-nothing semantics.
        normalized: list[dict[str, Any]] = []
        for i, raw in enumerate(children, start=1):
            existing_id = raw.get("student_id")
            class_id = raw.get("class_id")
            if not class_id:
                raise ValueError(f"Enfant {i}: la classe est obligatoire")
            cls = self.repo.class_info(self.school_id, UUID(str(class_id)))
            if not cls or UUID(str(cls["academic_year_id"])) != UUID(str(year["id"])) or not bool(cls.get("enabled", True)):
                raise ValueError(f"Enfant {i}: classe inactive ou hors année active")
            if not self._class_allowed(cls):
                raise PermissionError(f"Enfant {i}: classe hors de votre périmètre")
            if existing_id:
                current = self.repo.get_student_unscoped(self.school_id, UUID(str(existing_id)))
                if not current:
                    raise ValueError(f"Enfant {i}: élève existant introuvable")
                if family_id and UUID(str(current["family_id"])) != family_id:
                    raise ValueError("Un élève existant ne peut pas être rattaché silencieusement à un autre foyer")
                normalized.append({**raw, "_existing": current, "_class": cls})
                continue
            labels={"last_name":"nom","middle_name":"postnom","first_name":"prénom","class_id":"classe","gender":"sexe","birth_date":"date de naissance","birth_place":"lieu de naissance","nationality":"nationalité","address":"adresse","previous_school":"école de provenance"}
            for field in required:
                value=raw.get(field)
                if value is None or (isinstance(value,str) and not value.strip()):
                    raise ValueError(f"Enfant {i}: {labels.get(field,field)} obligatoire selon la politique d'inscription")
            normalized.append({**raw, "_existing": None, "_class": cls})

        if family_id:
            family = self.repo.get_family(self.school_id, family_id, scopes=self.permitted_scopes)
            if not family:
                raise ValueError("Foyer sélectionné introuvable ou hors de votre périmètre")
            if household_query and household_query.strip():
                candidates = self.repo.resolve_households(self.school_id, household_query, scopes=self.permitted_scopes)
                chosen = next((c for c in candidates if UUID(str(c["id"])) == family_id), None)
                if not chosen:
                    raise ValueError("Le foyer choisi ne correspond pas aux candidats de résolution visibles")
                self.repo.record_household_resolution(
                    self.school_id, query_text=household_query, selected_family_id=family_id,
                    confidence=str(chosen.get("confidence") or household_confidence or "POSSIBLE"),
                    candidate_count=len(candidates), resolution="CONFIRMED_EXISTING", actor_user_id=self.actor_user_id,
                )
        else:
            first = normalized[0]
            guardian_name = (primary_guardian or {}).get("full_name")
            student_name = " ".join(str(first.get(k) or "").strip() for k in ("last_name", "middle_name", "first_name")).strip()
            label, origin = generate_family_label(guardian_name=guardian_name, student_name=student_name)
            family_obj = Family(
                school_id=self.school_id,
                code=self.repo.next_code(self.school_id, "FAMILY", "FAM"),
                display_name=label,
                display_name_origin=origin,
                phone=(primary_guardian or {}).get("phone"),
                email=(primary_guardian or {}).get("email"),
                address=(primary_guardian or {}).get("address"),
                contact_status=ContactStatus.COMPLETE if guardian_name and ((primary_guardian or {}).get("phone") or (primary_guardian or {}).get("email")) else ContactStatus.TO_COMPLETE,
                notes=admission_notes,
            )
            family = self.repo.create_family(family_obj)
            family_id = family_obj.id
            guardians = ([primary_guardian] if primary_guardian else []) + list(additional_guardians or [])
            for idx, item in enumerate(x for x in guardians if x):
                name = str(item.get("full_name") or "").strip()
                if not name:
                    continue
                guardian = Guardian(
                    school_id=self.school_id,
                    full_name=name,
                    phone=item.get("phone"), email=item.get("email"), address=item.get("address"),
                    occupation=item.get("occupation"), notes=item.get("notes"),
                )
                self.repo.create_guardian(guardian)
                self.repo.link_guardian(
                    self.school_id, family_id=family_id, guardian_id=guardian.id,
                    role=str(item.get("role") or GuardianRole.TUTEUR.value), is_primary=bool(item.get("is_primary", idx == 0)),
                )
            self.repo.record_household_resolution(
                self.school_id, query_text=household_query, selected_family_id=family_id,
                confidence=household_confidence if household_confidence in {"CERTAIN", "POSSIBLE", "NONE"} else "NONE",
                candidate_count=0, resolution="CREATED_NEW", actor_user_id=self.actor_user_id,
            )

        student_ids: list[UUID] = []
        enrollment_ids: list[UUID] = []
        for item in normalized:
            existing = item["_existing"]
            if existing:
                student_id = UUID(str(existing["id"]))
                if UUID(str(existing["family_id"])) != family_id:
                    raise ValueError("Réinscription interdite hors du foyer permanent de l’élève")
                kind = "REENROLLMENT"
            else:
                student = Student(
                    school_id=self.school_id, family_id=family_id,
                    matricule=self.repo.next_code(self.school_id, "STUDENT", "ELV"),
                    last_name=str(item["last_name"]), middle_name=str(item["middle_name"]), first_name=str(item["first_name"]),
                    gender=item.get("gender"), birth_date=item.get("birth_date"), birth_place=item.get("birth_place"),
                    nationality=item.get("nationality"), address=item.get("address"), previous_school=item.get("previous_school"),
                    notes=item.get("notes"),
                )
                self.repo.create_student(student)
                student_id = student.id
                kind = "TRANSFER_IN" if item.get("origin") == "TRANSFER_IN" else "NEW"
            enrollment = Enrollment(
                school_id=self.school_id, student_id=student_id,
                academic_year_id=UUID(str(year["id"])), class_id=UUID(str(item["class_id"])),
                enrollment_kind=kind, origin_school=item.get("origin_school"), notes=item.get("enrollment_notes"),
            )
            self.repo.create_enrollment(enrollment)
            student_ids.append(student_id); enrollment_ids.append(enrollment.id)

            staff_id = item.get("staff_member_id")
            if staff_id:
                self.repo.link_staff_child(self.school_id, staff_id=UUID(str(staff_id)), student_id=student_id)
                if bool(item.get("staff_beneficiary")):
                    self.repo.add_benefit(StudentBenefit(
                        school_id=self.school_id, student_id=student_id, academic_year_id=UUID(str(year["id"])),
                        kind=BenefitKind.STAFF_CHILD, source_reference=str(staff_id), selected_explicitly=True,
                        configured_percent=_discount_from_policy(staff_policy),
                        applies_to_fee_code=(staff_policy or {}).get("applies_to_fee_code") or "SCOLARITE",
                    ))

        # Desktop: family-size eligibility is computed from validated enrollments against the year's policy; the
        # beneficiary remains explicit (manual) and keeps the policy rate.
        # Desktop _update_large_family_eligibility: eligible when the year's policy is enabled and the threshold is reached.
        eligible = False
        if large_policy is not None:
            minimum = int(large_policy.get("min_children") or 0)
            eligible = self.repo.count_family_enrolled_children(self.school_id, family_id, UUID(str(year["id"]))) >= minimum
            if large_selected and not eligible:
                raise ValueError(f"Bénéficiaire famille nombreuse impossible : le foyer n’atteint pas le seuil de {minimum} enfant(s) inscrits")
        for item, sid in zip(normalized, student_ids):
            if item.get("large_family_beneficiary"):
                self.repo.add_benefit(StudentBenefit(
                    school_id=self.school_id, student_id=sid, academic_year_id=UUID(str(year["id"])),
                    kind=BenefitKind.LARGE_FAMILY, source_reference=str(family_id), selected_explicitly=True,
                    configured_percent=_discount_from_policy(large_policy),
                    applies_to_fee_code=(large_policy or {}).get("applies_to_fee_code") or "SCOLARITE",
                ))

        return {
            "family_id": str(family_id), "student_ids": [str(x) for x in student_ids],
            "enrollment_ids": [str(x) for x in enrollment_ids], "count": len(student_ids),
            "large_family_eligible": eligible,
        }


def _discount_from_policy(policy: dict | None) -> Decimal:
    """Desktop _discount_from_policy: free beneficiaries means 100 %, otherwise the configured percent."""
    if not policy:
        return Decimal("0")
    if int(policy.get("free_beneficiaries") or 0) > 0:
        return Decimal("100")
    return Decimal(str(policy.get("discount_percent") or 0))
