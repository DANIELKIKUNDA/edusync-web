from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(x): return (ROOT/x).read_text(encoding="utf-8")
def test_audit_is_server_paginated():
 s=read("backend/src/edusync/modules/audit/api/router.py"); assert "cursor_at:datetime|None=None" in s and "(occurred_at,id) <" in s and "has_more" in s
def test_personnel_history_is_paginated():
 s=read("backend/src/edusync/modules/personnel/api/router.py"); assert "offset:int=Query(default=0,ge=0)" in s and "has_more" in s
def test_stewardship_heavy_lists_are_paginated():
 s=read("backend/src/edusync/modules/stewardship/api/router.py");
 for fn in ["stock","movement_list","assets","locations","count_list"]: assert f"def {fn}(limit:int=Query" in s
 assert s.count("OFFSET :offset") >= 4
