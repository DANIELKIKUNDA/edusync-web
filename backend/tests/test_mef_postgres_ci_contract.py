from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_mef_real_postgres_gate_is_wired_into_ci():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    script = (ROOT / "tools/ci/mef_postgres_integration.py").read_text(encoding="utf-8")
    assert "MEF — PostgreSQL réel, RLS, concurrence et créances annuelles" in workflow
    assert "mef_postgres_integration.py" in workflow
    for proof in ("finance_exigibility_policies", "finance_exigibility_assessments", "ThreadPoolExecutor",
                  "NOT_APPLICABLE", "NOT_EXIGIBLE", "2028, 2, 29", "Base distante refusée"):
        assert proof in script
