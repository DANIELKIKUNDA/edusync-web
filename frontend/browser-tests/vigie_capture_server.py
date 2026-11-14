"""Local-only visual fixture for Vigie screenshots (never used by the application or deployment)."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import json, os

DIST=Path(__file__).resolve().parents[1]/"dist"
school={"id":"sch-vigie","code":"EXC","name":"Excellencia Collège Riziki"}
user={"id":"u-promoteur","full_name":"Daniel Kikunda","email":"promoteur@example.test"}
permissions=["notifications.internal.read","notifications.internal.dismiss","communications.read","communications.history.read","dashboard.school.read","finance.recovery.monthly.read","finance.cash.other.read","settings.tariffs.read"]
nav=[{"key":"home","label":"Accueil","icon":"home"},{"key":"finance","label":"Finances","icon":"finance"},{"key":"supervision","label":"Surveillance","icon":"pulse"},{"key":"communications","label":"Communication","icon":"bell"}]
items=[
 {"id":"1","rule_code":"FINANCE_CLASS_INSOLVENCY","domain":"FINANCE","severity":"CRITICAL","condition_status":"OPEN","response_status":"NEW","title":"Risque financier élevé — 4e HSC","summary":"18 élèves sur 30 ont au moins deux mensualités impayées (60 %).","explanation":"La proportion dépasse le seuil de surveillance de 35 % et concerne au moins trois élèves.","recommendation":"Ouvrez le recouvrement de cette classe, vérifiez les causes et assignez une action de relance.","metric_json":{"late":18,"total":30},"target_path":"/finance?view=recovery&class=c4","opened_at":"2026-11-09T12:00:00Z","last_seen_at":"2026-11-09T15:00:00Z","resolved_at":None,"reminder_count":1},
 {"id":"2","rule_code":"CASH_SESSION_NOT_CLOSED","domain":"CASH","severity":"CRITICAL","condition_status":"OPEN","response_status":"ACKNOWLEDGED","title":"Caisse non clôturée","summary":"La caisse de Mme Kabwe est ouverte depuis 27 heures.","explanation":"Une caisse d’une journée antérieure est toujours ouverte et compromet le contrôle quotidien.","recommendation":"Demandez la clôture et vérifiez le journal avant toute réouverture.","metric_json":{"hours_open":27},"target_path":"/finance?view=cash&session=s2","opened_at":"2026-11-08T12:00:00Z","last_seen_at":"2026-11-09T15:00:00Z","resolved_at":None,"reminder_count":2},
 {"id":"3","rule_code":"ENROLLMENTS_WITHOUT_CHARGES","domain":"CONFIGURATION","severity":"WARNING","condition_status":"OPEN","response_status":"NEW","title":"Obligations financières manquantes","summary":"7 inscriptions validées n’ont aucune obligation financière active.","explanation":"Ces élèves peuvent apparaître comme en ordre alors qu’aucun frais n’a été généré.","recommendation":"Vérifiez les barèmes et régénérez les obligations.","metric_json":{"enrollments":7},"target_path":"/settings?view=tariffs","opened_at":"2026-11-09T12:00:00Z","last_seen_at":"2026-11-09T15:00:00Z","resolved_at":None,"reminder_count":1}]

class H(SimpleHTTPRequestHandler):
 def do_GET(self):
  p=self.path.split("?",1)[0]
  if p.startswith("/api/v1/"):
   key=p.removeprefix("/api/v1")
   if key=="/auth/refresh": body={"access_token":"fixture","scope":"SCHOOL","school":school,"user":user,"permissions":permissions}
   elif key=="/auth/contexts": body={"contexts":[],"current":{"scope":"SCHOOL"},"current_valid":True}
   elif key=="/access/me": body={"membership_id":"m","school_id":school["id"],"role_label":"Promoteur","permissions":permissions,"scoped":[],"roles":[],"navigation":nav,"widgets":[],"actions":[]}
   elif key=="/settings/academic-years": body=[]
   elif key=="/supervision/incidents": body={"counts":{"active":4,"critical":2,"new":3},"items":items}
   elif key=="/notifications/inbox": body={"items":[],"unread":0,"next_cursor":None}
   else: body={"items":[],"total":0}
   raw=json.dumps(body,ensure_ascii=False).encode();self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw);return
  if p=="/": self.path="/index.html"
  return super().do_GET()
 def log_message(self,*_): pass

if __name__=="__main__": os.chdir(DIST);ThreadingHTTPServer(("127.0.0.1",5182),H).serve_forever()
