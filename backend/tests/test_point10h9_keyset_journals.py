from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p): return (ROOT/p).read_text(encoding='utf-8')
def test_audit_uses_keyset_not_offset():
 s=read('backend/src/edusync/modules/audit/api/router.py'); block=s[s.index("@router.get('/events')"):s.index("@router.get('/entities")]
 assert 'cursor_at' in block and '(occurred_at,id) <' in block and 'OFFSET' not in block and 'count(*)' not in block
 assert "'has_more':has_more" in block and "'next_cursor'" in block
def test_sync_conflicts_and_outbox_are_keyset_paginated():
 s=read('backend/src/edusync/modules/sync/api/router.py')
 assert "@router.get('/outbox/pending')" in s
 assert "(received_at,id) <" in s and "(created_at,id) <" in s
 assert s.count("'next_cursor'") >= 2
def test_keyset_indexes_match_ordering():
 s=read('backend/migrations/0029_keyset_journal_indexes.sql')
 for x in ['audit_events(school_id, occurred_at DESC, id DESC)','sync_inbox(school_id, received_at DESC, id DESC)', 'outbox_events(school_id, created_at DESC, id DESC)']: assert x in s
