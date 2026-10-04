from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p): return (ROOT/p).read_text(encoding='utf-8')
def test_point9_schema_is_tenant_auditable_and_separates_sale_stock():
 s=read('backend/migrations/0024_stewardship_industrial.sql')
 for x in ['inventory_locations','inventory_items','inventory_item_movements','inventory_assets','inventory_asset_events','inventory_counts','inventory_count_lines','FORCE ROW LEVEL SECURITY']: assert x in s
 assert 'Existing Point 6B sale stock remains authoritative' in s
def test_point9_permissions_fail_closed_and_reason_required():
 s=read('backend/src/edusync/modules/stewardship/api/router.py')
 for x in ['inventory.stock.read','inventory.stock.receive','inventory.stock.issue','inventory.stock.adjust','inventory.assets.read']: assert x in s
 assert "reason:str=Field(min_length=3" in s and 'Stock insuffisant' in s
def test_point9_ui_is_permission_driven():
 a=read('frontend/src/App.tsx'); h=read('frontend/src/home.tsx'); u=read('frontend/src/stewardship.tsx')
 assert "stewardship:['inventory.']" in a
 assert "inventory.assets.create" in h and "inventory.assets.manage" not in h
 assert 'Intendance possède le stock; le Centre financier reste propriétaire de l’encaissement.' in u
def test_secondary_directors_baseline_excludes_finance_and_personnel():
 s=read('backend/migrations/0024_stewardship_industrial.sql')
 assert "r.code IN ('DIRECTEUR_ETUDES','DIRECTEUR_DISCIPLINE')" in s
 assert "rc.capability_code LIKE 'finance.%'" in s and "rc.capability_code LIKE 'personnel.%'" in s
