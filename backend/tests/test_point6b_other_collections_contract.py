from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def read(p): return (ROOT/p).read_text(encoding='utf-8')
def test_other_collections_is_plain_language_and_no_duplicate_anticipation():
 s=read('frontend/src/finance.tsx')
 assert 'Autres encaissements' in s
 assert 'Outils spécialisés' not in s
 assert 'Paiement anticipé' not in s
 assert 'Vente d’articles' in s
 assert 'Dettes antérieures' in s
def test_product_sale_is_stock_atomic_and_reference_not_manual():
 s=read('backend/src/edusync/adapters/postgres_finance_checkout.py')
 assert 'FOR UPDATE' in s and 'Stock insuffisant' in s
 assert "movement_type,quantity_delta" in s and "'SALE'" in s
 ui=read('frontend/src/finance.tsx')
 assert 'aucune référence technique n’est à saisir au guichet' in ui
 assert 'Encaisser la vente' in ui
def test_old_debt_is_transannual_without_switching_active_year():
 s=read('backend/src/edusync/adapters/postgres_finance_checkout.py')
 assert "y.status IN ('CLOSED','ARCHIVED')" in s
 ui=read('frontend/src/finance.tsx')
 assert 'sans changer l’année scolaire active' in ui
 assert 'sans changer l’année scolaire de l’application' in ui
def test_stock_belongs_to_inventory_domain():
 m=read('backend/migrations/0018_finance_other_collections_inventory.sql')
 assert 'inventory_stock' in m and 'inventory_stock_movements' in m
 assert 'finance_product_sales' in m
