"""Update flow of the installed app (audit 2026-11-01, standard « prompt for update »): a new version downloads in the
background and waits; the notice appears once it is on the device; « Mettre à jour » activates it and reloads once from
the device; a screen of an old build never ends on an error after a deployment."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
F = ROOT / "frontend"
SW = (F / "public/sw.js").read_text(encoding="utf-8")
UP = (F / "src/platform/updates.ts").read_text(encoding="utf-8")


def test_new_version_waits_and_downloads_before_it_is_offered():
    install = SW.split("self.addEventListener('install'", 1)[1].split("});\n", 1)[0]
    assert "precacheInto(cache)" in install                                  # the whole new app is downloaded first
    assert "if(!self.registration.active)await self.skipWaiting()" in install  # only the very first install takes over
    assert "self.skipWaiting();" not in install.replace("await self.skipWaiting()", "")
    assert "EDUSYNC_SKIP_WAITING" in SW                                      # the user decides the moment


def test_the_app_opens_from_the_device_and_old_copies_go_only_on_activation():
    nav = SW.split("request.mode==='navigate'", 1)[1].split("return;", 1)[0]
    assert "caches.open(CACHE).then(cache=>cache.match('/'))" in nav and "fetch(request)" in nav
    assert "'/icons/edusync-mark.svg'" in SW.split("const SHELL=", 1)[1].split(";", 1)[0]
    activate = SW.split("self.addEventListener('activate'", 1)[1].split("});", 1)[0]
    assert "caches.delete" in activate


def test_notice_appears_when_downloaded_and_click_reloads_once_without_network():
    assert "reg.waiting" in UP and "w.state === 'installed'" in UP and "READY_FALLBACK_MS" in UP
    apply = UP.split("export async function applyUpdate", 1)[1].split("\n}\n", 1)[0]
    assert "reg.update()" not in apply and "EDUSYNC_SKIP_WAITING" in apply and "window.location.reload()" in apply
    assert "Installation de la mise à jour" in (F / "public/boot-fallback.js").read_text(encoding="utf-8")


def test_old_build_screens_recover_by_one_guarded_reload():
    lazy = (F / "src/platform/lazy_page.ts").read_text(encoding="utf-8")
    assert "GUARD_MS" in lazy and "vite:preloadError" in lazy and "navigator.onLine === false" in lazy
    app = (F / "src/App.tsx").read_text(encoding="utf-8")
    assert "=lazy(()=>import(" not in app and "=lazyPage(()=>import(" in app
    sb = (F / "src/platform/screen_boundary.tsx").read_text(encoding="utf-8")
    assert sb.index("dynamically imported module") < sb.index("Connexion impossible")   # a deployment, not a lost network
