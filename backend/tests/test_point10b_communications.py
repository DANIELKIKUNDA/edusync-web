from pathlib import Path
R=Path(__file__).resolve().parents[2]
def read(p):return (R/p).read_text()
def test_communications_schema_is_tenant_and_delivery_aware():
 s=read('backend/migrations/0025_communications_industrial.sql');assert all(x in s for x in ['communication_templates','communication_messages','communication_deliveries','FORCE ROW LEVEL SECURITY','provider_message_id','estimated_segments'])
def test_external_delivery_is_optional_fail_closed():
 s=read('backend/src/edusync/modules/communications/api/router.py');assert 'Canal externe non activé' in s and 'Fournisseur SMS ou expéditeur non configuré' in s and "'QUEUED'" in s
def test_redis_is_queue_not_truth():
 s=read('backend/src/edusync/modules/communications/worker.py');assert 'PostgreSQL remains source of truth' in s and "brpop('edusync:communications'" in s and 'PROVIDER_NOT_CONFIGURED' in s
def test_existing_scope_capabilities_are_reused():
 s=read('backend/src/edusync/modules/communications/api/router.py');assert all(x in s for x in ['communications.send.individual','communications.send.class','communications.send.section','communications.send.all_parents','communications.sms.bulk_send'])
def test_sms_segment_estimator():
 from edusync.modules.communications.domain.models import sms_segments
 assert sms_segments('a'*160)==1 and sms_segments('a'*161)==2 and sms_segments('é'*71)==2
def test_router_registered():
 s=read('backend/src/edusync/bootstrap/app.py');assert '/api/v1/communications' in s
