from pathlib import Path
UI=Path('../frontend/src/finance.tsx').read_text(encoding='utf-8')
def test_fast_search_and_family_flow_present():
 for s in ['Recherche globale','180','Ajouter un enfant','Échéance suivante','Effacer','Encaisser maintenant']:assert s in UI
def test_receipt_print_is_not_automatic():
 assert '.print(' not in UI and 'L’impression reste un choix séparé' in UI
def test_permission_gates_collect():assert "finance.checkout.collect" in UI

def test_anticipation_is_integrated_in_same_checkout():
 for s in ['Montant remis par le parent','Paiement avec avance','checkoutAnticipation','Échéance suivante']:assert s in UI


def test_first_payment_can_activate_advance_plan_without_pre_enrollment():
 for text in ['Paiement normal','Paiement avec avance','Participation possible dès ce paiement','Confirmer le paiement avec avance ?','EduSync retiendra ce choix']:
  assert text in UI
 assert 'aucun plan anticipé accepté pour cet élève' not in UI

def test_cashier_ui_hides_accounting_complexity():
 assert 'Fonds anticipés' not in UI
 assert 'Mis en avance' in UI
