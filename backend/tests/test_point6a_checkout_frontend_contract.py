from pathlib import Path
UI=Path('../frontend/src/finance.tsx').read_text(encoding='utf-8')
def test_fast_search_and_family_flow_present():
 for s in ['Recherche globale','180','Ajouter un enfant','Action conseillée','Effacer','Encaisser maintenant']:assert s in UI
def test_receipt_print_is_not_automatic():
 # A receipt preview and direct browser print exist; neither runs automatically after payment.
 assert 'function printPdfDirectly' in UI and 'onClick={()=>void printReceiptNow(' in UI and "onClick={()=>{try{frame.current?.contentWindow?.focus();frame.current?.contentWindow?.print()}" in UI and 'L’impression reste un choix séparé' in UI
def test_permission_gates_collect():assert "finance.checkout.collect" in UI

def test_anticipation_is_integrated_in_same_checkout():
 # Parity lot L6 (owner decision 2026-10-14): the plan payment lives in the same checkout, Desktop model.
 for s in ['Montant remis par le parent','Paiement selon un plan anticipé','checkoutPlans','checkoutCollectPlan','Action conseillée']:assert s in UI


def test_plan_membership_and_mandatory_first_payment():
 # Optional plan: the parent joins or declines; mandatory plan: membership recorded with the first plan payment.
 for text in ['Adhérer au plan','Refuser','Adhésion automatique au premier paiement selon le plan','Confirmer le paiement selon le plan ?','Ce plan est obligatoire']:
  assert text in UI
 # The former simplified plan (surplus kept as a provision) is retired from the cash desk.
 for old in ['Paiement avec avance','use_anticipation','Mis en avance','checkoutAnticipation']:
  assert old not in UI

def test_cashier_ui_hides_accounting_complexity():
 assert 'Fonds anticipés indisponibles' in UI
 assert 'aucun montant mis en réserve' in UI and 'Mois courant d’abord, puis uniquement les mois cibles du plan' in UI
