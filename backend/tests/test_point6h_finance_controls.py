from pathlib import Path
from edusync.modules.finance_controls.domain.models import credit_remaining,VALID_DECISIONS,VALID_RESPONSIBILITIES
ROOT=Path(__file__).parents[2]
def test_finance_control_domains_are_explicit():
 assert {'EXEMPTION','DISCOUNT','THIRD_PARTY_COVERAGE'}<=VALID_DECISIONS and 'REDUCTION' not in VALID_DECISIONS  # N3-C: Desktop natures
 assert {'FAMILY','PAYROLL','SCHOOL','THIRD_PARTY'}==VALID_RESPONSIBILITIES
 assert credit_remaining('100','25')==75
def test_credit_is_not_a_manual_cashier_mutation():
 reg=(ROOT/'contracts'/'CAPABILITY_REGISTRY.json').read_text()
 assert 'finance.credits.read' in reg
 assert 'finance.credits.create' not in reg and 'finance.credits.delete' not in reg
def test_ui_removes_operator_bucket_and_keeps_dense_tables():
 src=(ROOT/'frontend'/'src'/'finance.tsx').read_text()
 assert 'Suivi opérateur' not in src
 for x in ('Décisions & exonérations','Responsabilités prévues','Crédits & trop-perçus'): assert x in src
 assert 'cashSummaryTable' in src
def test_migration_is_tenant_isolated_and_append_or_cancel():
 sql=(ROOT/'backend'/'migrations'/'0022_finance_controls.sql').read_text()
 for table in ('finance_decisions','finance_responsibilities','finance_credits'):
  assert f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY' in sql
  assert f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY' in sql
 assert "status IN ('ACTIVE','CANCELLED')" in sql
