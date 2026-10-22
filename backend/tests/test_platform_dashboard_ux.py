"""Lot UX plateforme 2026-10: dashboard (single source of truth, capability-aware), profile photo, account dock."""
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

import pytest

from edusync.modules.platform.application.dashboard import active_schools_trend, month_starts
from edusync.shared.infrastructure.avatars import AVATAR_SIDE, avatar_key, process_avatar

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "backend/src/edusync"
FRONT = ROOT / "frontend/src"
NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)


def d(y, m, day=15):
    return datetime(y, m, day, tzinfo=timezone.utc)


# ---------------------------------------------------------------- trend
def test_month_starts_are_the_last_months_oldest_first():
    months = month_starts(NOW, 6)
    assert [m.strftime("%Y-%m") for m in months] == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert [m.strftime("%Y-%m") for m in month_starts(datetime(2026, 2, 3, tzinfo=timezone.utc), 3)] == ["2025-12", "2026-01", "2026-02"]


def test_trend_follows_creations_and_audited_suspensions_and_ends_on_the_live_figure():
    schools = [{"id": "a", "created_at": d(2026, 5), "status": "ACTIVE"},
               {"id": "b", "created_at": d(2026, 7), "status": "SUSPENDED"},
               {"id": "c", "created_at": d(2026, 9), "status": "ACTIVE"}]
    events = [{"school_id": "b", "occurred_at": d(2026, 8, 10), "action": "SCHOOL_SUSPENDED"}]
    pts = {p["month"]: p["active"] for p in active_schools_trend(schools, events, NOW, 6)}
    assert pts == {"2026-05": 1, "2026-06": 1, "2026-07": 2, "2026-08": 1, "2026-09": 2, "2026-10": 2}


def test_reactivation_counts_again_and_legacy_schools_keep_their_status():
    schools = [{"id": "a", "created_at": d(2026, 1), "status": "ACTIVE"}, {"id": "old", "created_at": d(2025, 1), "status": "DISABLED"}]
    events = [{"school_id": "a", "occurred_at": d(2026, 6, 2), "action": "SCHOOL_SUSPENDED"},
              {"school_id": "a", "occurred_at": d(2026, 8, 20), "action": "SCHOOL_REACTIVATED"}]
    pts = [p["active"] for p in active_schools_trend(schools, events, NOW, 6)]
    assert pts == [1, 0, 0, 1, 1, 1]


def test_no_school_means_no_trend_data():
    pts = active_schools_trend([], [], NOW, 6)
    assert len(pts) == 6 and not any(p["active"] for p in pts)


# ---------------------------------------------------------------- capability-aware dashboard (contract)
def test_dashboard_reveals_nothing_beyond_the_actor_capabilities():
    src = (SRC / "modules/platform/application/dashboard.py").read_text(encoding="utf-8")
    assert 'if "platform.audit.read" in permissions:' in src and '"recent_activity": recent' in src      # activity: audit capability only
    assert 'if "platform.health.read" in permissions:' in src                                           # technical items: health capability
    assert '"tone": "action" if can_fix else "info"' in src                                             # an action only for whoever can act
    assert 'sum(w["count"] for w in watch if w["tone"] == "action")' in src                              # KPI = actionable items (same payload)
    assert "LIMIT 5" in src
    router = (SRC / "modules/platform/api/router.py").read_text(encoding="utf-8")
    assert "actor.require('platform.schools.read')" in router.split("def platform_dashboard", 1)[1][:400]
    assert "managers = _active_managers(c) if TEAM_CAP in perms else None" in router


def test_kpi_and_detail_views_share_one_definition():
    router = (SRC / "modules/platform/api/router.py").read_text(encoding="utf-8")
    dash = (SRC / "modules/platform/application/dashboard.py").read_text(encoding="utf-8")
    assert "'total':total" in router.split("def platform_schools_page", 1)[1] and "'total':total" in router.split("def platform_access", 1)[1]
    # "Accès actifs": active account holding an active school membership, in both places
    assert "u.active AND EXISTS (SELECT 1 FROM school_memberships m2 WHERE m2.user_id=u.id AND m2.active)" in router
    assert "WHERE u.active\n        AND EXISTS (SELECT 1 FROM school_memberships m WHERE m.user_id=u.id AND m.active)" in dash
    # "sans administrateur": active school without an active ADMIN_SYSTEME_ECOLE, in both places
    # the schools directory SQL moved to application/schools_directory.py (schools module lot 2026-10)
    directory = (SRC / "modules/platform/application/schools_directory.py").read_text(encoding="utf-8")
    assert "r2.code='ADMIN_SYSTEME_ECOLE'" in directory and "SCHOOL_ADMIN_ROLE = \"ADMIN_SYSTEME_ECOLE\"" in dash


def test_frontend_kpi_cards_are_whole_buttons_without_a_view_link():
    tsx = (FRONT / "platform/dashboard.tsx").read_text(encoding="utf-8")
    assert tsx.count('className={`pd-kpi ') == 1 and '<button key={c.key} type="button"' in tsx and "aria-label={c.aria}" in tsx
    assert ">Voir<" not in tsx and "Voir toute l’activité" in tsx
    for label in ("Écoles", "Écoles actives", "Accès actifs", "Actions requises"):
        assert f"label: '{label}'" in tsx, label
    for cap in ("platform.schools.create", "platform.collaborators.manage", "platform.school_admin.bootstrap"):
        assert f"has('{cap}')" in tsx, cap                                   # quick actions from capabilities, never a role name
    assert "MANAGER_SYSTEME" not in tsx
    assert "Aucune tendance disponible pour le moment." in tsx and "La courbe apparaîtra avec l’activation des premières écoles." in tsx


def test_account_dock_preferences_and_no_atelier_pro_left_in_scope():
    app = (FRONT / "App.tsx").read_text(encoding="utf-8")
    shell = (FRONT / "platform/shell.tsx").read_text(encoding="utf-8")
    account = (FRONT / "platform/account.tsx").read_text(encoding="utf-8")
    assert "<AppShell accountDock" in app and "label:'Préférences'" in app and "Plateforme EduSync · ${role}" in app
    assert "function SideAccount" in shell and "function DrawerAccount" in shell and "aria-expanded={open}" in shell
    assert "export function PreferencesDialog" in account and "Atelier" not in account
    scope = app.split("function AtelierPro", 1)[1].split("function PlatformSchoolDetailDialog", 1)[0] + app.split("function Shell(", 1)[1].split("\n", 1)[0]
    assert "Atelier Pro" not in scope
    theme = (FRONT / "platform/theme.ts").read_text(encoding="utf-8")
    assert "prefers-color-scheme: dark" in theme and "localStorage.setItem(key(account), p)" in theme


# ---------------------------------------------------------------- profile photo
def _jpeg_with_gps(w=900, h=600) -> bytes:
    from PIL import Image
    img = Image.new("RGB", (w, h), (30, 90, 200))
    exif = Image.Exif()
    exif[0x0110] = "Camera-Model-Secret"
    exif[0x8825] = {1: "N", 2: (4.0, 19.0, 0.0)}                            # GPS block
    out = BytesIO()
    img.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def test_photo_is_reencoded_as_a_square_webp_without_metadata():
    from PIL import Image
    raw = _jpeg_with_gps()
    assert b"Camera-Model-Secret" in raw
    webp, digest = process_avatar(raw)
    assert webp[:4] == b"RIFF" and webp[8:12] == b"WEBP" and b"Camera-Model-Secret" not in webp and b"Exif" not in webp
    with Image.open(BytesIO(webp)) as img:
        assert img.size == (AVATAR_SIDE, AVATAR_SIDE)
    assert len(digest) == 64 and avatar_key("u1", digest) == f"users/u1/avatar-{digest[:24]}.webp"


@pytest.mark.parametrize("data,needle", [
    (b"", "vide"), (b"<svg onload=alert(1)>", "Format refusé"), (b"GIF89a" + b"0" * 100, "Format refusé"),
    (b"\x89PNG\r\n\x1a\n" + b"garbage" * 20, "illisible"), (b"\xff\xd8\xff" + b"0" * (5 * 1024 * 1024 + 1), "5 Mo"),
], ids=["vide", "svg", "gif", "png-corrompu", "trop-lourd"])
def test_photo_refusals(data, needle):
    with pytest.raises(ValueError) as e:
        process_avatar(data)
    assert needle in str(e.value)


def test_tiny_photo_is_refused():
    from PIL import Image
    out = BytesIO(); Image.new("RGB", (20, 20)).save(out, format="PNG")
    with pytest.raises(ValueError):
        process_avatar(out.getvalue())


def test_photo_routes_are_own_account_only_private_and_audited():
    src = (SRC / "modules/iam/api/router.py").read_text(encoding="utf-8")
    part = src.split("# ---------------------------------------------------------------- profile photo", 1)[1]
    assert part.count("Depends(require_platform_actor)") == 3 and "actor.user_id" in part and "user_id=:u" in part
    assert 'startswith(f"users/{actor.user_id}/avatar-")' in part and '"private, max-age=600"' in part and "nosniff" in part
    assert "USER_AVATAR_UPDATED" in part and "USER_AVATAR_REMOVED" in part
    mig = (ROOT / "backend/migrations/0077_user_avatars.sql").read_text(encoding="utf-8")
    assert "FORCE ROW LEVEL SECURITY" in mig and "REVOKE ALL ON user_avatars FROM edusync_tenant" in mig
    assert '("0077_user_avatars", "0077_user_avatars.sql")' in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------- update notice + bell on phones (owner feedback)
def test_new_version_is_announced_and_applied_safely():
    vite = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    assert "__EDUSYNC_BUILD__" in vite and "fileName: 'version.json'" in vite and "EDUSYNC_BUILD_ID" in vite
    assert "ARG EDUSYNC_BUILD_ID" in (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
    assert "build-args: EDUSYNC_BUILD_ID=${{ github.sha }}" in (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    assert "location = /version.json" in nginx and 'Cache-Control "no-store"' in nginx
    sw = (ROOT / "frontend/public/sw.js").read_text(encoding="utf-8")
    # never served from the SW cache: /version.json is part of the early bypass of the fetch handler (before any respondWith)
    bypass = next(line for line in sw.splitlines() if "url.pathname.startsWith('/api/')" in line)
    assert bypass.strip().startswith("if(") and bypass.rstrip().endswith("return;") and "'/version.json'" in bypass
    assert sw.index(bypass) < sw.index("event.respondWith(") and "EDUSYNC_SKIP_WAITING" in sw
    up = (FRONT / "platform/updates.ts").read_text(encoding="utf-8")
    assert "POLL_MS = 5 * 60 * 1000" in up and "'visibilitychange'" in up and "'online'" in up
    assert "hasUnsavedForms()" in up and "activity.pending > 0" in up and "confirmAction(" in up     # never loses work silently
    assert "window.location.reload()" in up and "EduSync est à jour" in up
    shell = (FRONT / "platform/shell.tsx").read_text(encoding="utf-8")
    assert "Nouvelle version disponible" in shell and "Mettre à jour" in shell and "<UpdateChip bar/>" in shell and "<UpdateChip/>{tools}" in shell


def test_notification_bell_is_not_hidden_on_phones():
    css = (FRONT / "platform/theme.css").read_text(encoding="utf-8")
    assert ".es-dock .es-tools .es-account{display:none}" not in css     # the bell reuses .es-account: never hide it
