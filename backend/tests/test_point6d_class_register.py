from decimal import Decimal
from edusync.modules.finance_recovery.domain.class_register import cell_value,recovery_rate,terminal_label

def test_terminal_labels_are_plain_language():
    assert terminal_label('ABANDON')=='Abandon';assert terminal_label('TRANSFER')=='Transféré'
def test_advance_is_visible_in_target_cell():
    assert cell_value(paid='65000',advance='15000',net='105000')=='80000'
def test_status_replaces_debt_display():
    assert cell_value(paid=0,advance=0,net=65000,status_label='Abandon')=='Abandon'
def test_rate_is_global_ratio():
    assert recovery_rate('200000','150000')==Decimal('75.0')
def test_no_fake_registration_from_june_payment():
    # Domain contract: a cell is driven by its charge identity, never by enrollment date or payment timing.
    assert cell_value(paid='7500',advance=0,net='7500')=='7500'
