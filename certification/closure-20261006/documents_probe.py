"""Live probe: documents on S3-compatible object storage (real API + PostgreSQL + SeaweedFS)."""
import hashlib
import json
import os
import sys
import time
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import BASE, owner, state, ensure_user, login, user_client  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def png(size=(256, 256), color=(15, 79, 191)):
    buf = BytesIO(); Image.new("RGB", size, color).save(buf, "PNG"); return buf.getvalue()


A, B = state["A"], state["B"]
admin_a = user_client(A, "ADMIN")
admin_b = user_client(B, "ADMIN")
cashier_a = user_client(A, "CAISSIER1")

check("stockage objet disponible", admin_a.get("documents/storage/status").json() == {"available": True})

# --- logo upload ----------------------------------------------------------------------------------
logo = png()
r = admin_a.put("documents/branding/logo", content=logo, headers={"Content-Type": "image/png"})
check("logo PNG accepté (administrateur)", r.status_code == 200 and r.json()["sha256"] == hashlib.sha256(logo).hexdigest(), r.status_code)
r = cashier_a.put("documents/branding/logo", content=logo, headers={"Content-Type": "image/png"})
check("logo refusé sans settings.documents.manage", r.status_code == 403, r.status_code)
r = admin_a.put("documents/branding/logo", content=b"<html><script>alert(1)</script></html>", headers={"Content-Type": "image/png"})
check("faux PNG (HTML déguisé) refusé", r.status_code == 422, r.text[:120])
r = admin_a.put("documents/branding/logo", content=b"\x89PNG\r\n\x1a\n" + os.urandom(2000), headers={"Content-Type": "image/png"})
check("PNG corrompu refusé", r.status_code == 422, r.text[:120])
r = admin_a.put("documents/branding/logo", content=png((8, 8)), headers={"Content-Type": "image/png"})
check("logo trop petit refusé", r.status_code == 422, r.text[:120])
big = BytesIO(); Image.frombytes("RGB", (1100, 1100), os.urandom(1100 * 1100 * 3)).save(big, "PNG")
r = admin_a.put("documents/branding/logo", content=big.getvalue(), headers={"Content-Type": "image/png"})
check("logo > 1 Mo refusé", r.status_code in (413, 422), f"{r.status_code} ({len(big.getvalue())} octets)")

r = admin_a.get("documents/branding/logo")
check("logo relu à l'identique (école A)", r.status_code == 200 and r.content == logo and r.headers["content-type"] == "image/png", r.status_code)
r = admin_b.get("documents/branding/logo")
check("école B ne voit pas le logo de A", r.status_code == 404 or (r.status_code == 200 and r.content != logo), r.status_code)

with owner.connect() as c:
    key = c.execute(text("SELECT logo_object_key FROM school_branding WHERE school_id=:s"), {"s": A["school_id"]}).scalar_one()
check("clé objet sous le préfixe de l'école", key.startswith(f"schools/{A['school_id']}/branding/"), key)
anon = httpx.get(os.environ["EDUSYNC_OBJECT_STORAGE_ENDPOINT"] + "/" + os.environ["EDUSYNC_OBJECT_STORAGE_BUCKET"] + "/" + key)
check("bucket privé : accès anonyme refusé", anon.status_code == 403, anon.status_code)
try:
    with owner.begin() as c:
        c.execute(text("UPDATE school_branding SET logo_object_key=:k WHERE school_id=:s"), {"k": f"schools/{B['school_id']}/branding/x.png", "s": A["school_id"]})
    check("contrainte base : clé d'une autre école impossible", False)
except Exception as exc:  # noqa: BLE001
    check("contrainte base : clé d'une autre école impossible", "check" in str(exc).lower() or "23514" in str(getattr(exc, "orig", "") and exc.orig.sqlstate), type(exc).__name__)

# --- generated documents archive ----------------------------------------------------------------
t = time.time()
r = admin_a.get("schooling/exports/students.pdf")
check("export PDF élèves (téléchargement inchangé)", r.status_code == 200 and r.content.startswith(b"%PDF"), f"{r.status_code} {time.time()-t:.1f}s")
pdf = r.content
check("le PDF intègre le logo stocké", b"/Image" in pdf or b"/XObject" in pdf)
h = admin_a.get("documents/history").json()
item = next((x for x in h["items"] if x["document_code"] == "students.directory" and x["format"] == "PDF"), None)
check("document archivé et listé dans l'historique", item is not None, [x["document_code"] for x in h["items"]][:6])
r2 = admin_a.get("schooling/exports/students.pdf")
h2 = admin_a.get("documents/history").json()
item2 = next((x for x in h2["items"] if x["document_code"] == "students.directory" and x["format"] == "PDF"), None)
check("même document régénéré : une version courante, historique conservé", item2 and item2["generations"] >= 2 and sum(1 for x in h2["items"] if x["document_code"] == "students.directory" and x["format"] == "PDF") == 1, item2 and item2["generations"])

link = admin_a.post(f"documents/history/{item2['id']}/link").json()
check("lien signé de courte durée", link["url"].startswith("/api/v1/documents/open?token=") and link["expires_at"] - time.time() <= 305, link["expires_at"] - time.time())
opened = httpx.get(BASE.replace("/api/v1", "") + link["url"])
check("ouverture du lien signé : PDF identique, inline", opened.status_code == 200 and opened.content == r2.content and opened.headers["content-disposition"].startswith("inline"), opened.status_code)
token = link["url"].split("token=")[1]
tampered = token[:-3] + ("AAA" if not token.endswith("AAA") else "BBB")
check("lien falsifié refusé", httpx.get(BASE + "/documents/open", params={"token": tampered}).status_code == 403)
from edusync.modules.documents.application.object_store import sign_link  # noqa: E402
from edusync.bootstrap.settings import Settings  # noqa: E402
old_tok, _ = sign_link(Settings(), document_id=item2["id"], school_id=A["school_id"], user_id=A["users"]["ADMIN"]["user_id"], now=time.time() - 3600)
check("lien expiré refusé", httpx.get(BASE + "/documents/open", params={"token": old_tok}).status_code == 403)
forged, _ = sign_link(Settings(), document_id=item2["id"], school_id=B["school_id"], user_id=B["users"]["ADMIN"]["user_id"])
check("lien pointant un document de A au nom de l'école B : refusé", httpx.get(BASE + "/documents/open", params={"token": forged}).status_code == 403)

check("école B : document de A introuvable (BOLA)", admin_b.post(f"documents/history/{item2['id']}/link").status_code == 404)
check("école B : historique sans document de A", all(x["id"] != item2["id"] for x in admin_b.get("documents/history").json()["items"]))

# Privilege: a cashier (documents.history.read) must not see archived personnel registers.
pr = admin_a.get("personnel/exports/register.pdf")
if pr.status_code == 200:
    hist_c = cashier_a.get("documents/history")
    codes = [x["document_code"] for x in hist_c.json()["items"]] if hist_c.status_code == 200 else []
    check("caissier : registre du personnel absent de son historique", "personnel.register" not in codes, codes[:8])
    pid = next(x["id"] for x in admin_a.get("documents/history").json()["items"] if x["document_code"] == "personnel.register")
    check("caissier : lien vers le registre du personnel refusé", cashier_a.post(f"documents/history/{pid}/link").status_code == 404)
else:
    check("export registre du personnel (administrateur)", False, pr.status_code)

# Membership revoked after link issued => link dies.
u = ensure_user(A, "CLOSURE_DOCS", ("SECRETARIAT",))
cu = login(u["email"], u["password"], "SCHOOL", A["code"])
exp = cu.get("schooling/exports/students.xlsx")
if exp.status_code == 200:
    did = next(x["id"] for x in cu.get("documents/history").json()["items"] if x["document_code"] == "students.directory" and x["format"] == "XLSX")
    lk = cu.post(f"documents/history/{did}/link").json()["url"]
    with owner.begin() as c:
        c.execute(text("UPDATE school_memberships SET active=false WHERE id=:m"), {"m": u["membership_id"]})
    check("accès retiré après émission du lien : lien refusé", httpx.get(BASE.replace("/api/v1", "") + lk).status_code == 403)
    with owner.begin() as c:
        c.execute(text("UPDATE school_memberships SET active=true WHERE id=:m"), {"m": u["membership_id"]})
else:
    check("export XLSX élèves (secrétariat)", False, exp.status_code)

with owner.connect() as c:
    bad = c.execute(text("SELECT count(*) FROM generated_documents WHERE object_key NOT LIKE 'schools/' || school_id::text || '/%'")).scalar_one()
    caps = c.execute(text("SELECT count(*) FROM generated_documents WHERE required_capability IS NULL AND generated_at > now() - interval '1 hour'")).scalar_one()
check("toutes les clés archivées sous le préfixe de leur école", bad == 0, bad)
check("chaque document récent porte sa permission productrice", caps == 0, caps)

out = Path(__file__).with_name("documents-live.json")
out.write_text(json.dumps({"passed": sum(x["pass"] for x in results), "total": len(results), "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{sum(x['pass'] for x in results)}/{len(results)} PASS")
sys.exit(0 if all(x["pass"] for x in results) else 1)
