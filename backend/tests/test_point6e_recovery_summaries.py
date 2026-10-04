from decimal import Decimal
from edusync.modules.finance_recovery.domain.summaries import total_row,register_footer

def test_class_monthly_total_does_not_sum_people():
 r=[{'debtors':20,'in_order':10,'not_in_order':10,'expected':100,'cash_collected':70,'outside_cash':10,'regularized_total':80,'remaining':20},{'debtors':19,'in_order':12,'not_in_order':7,'expected':90,'cash_collected':70,'outside_cash':0,'regularized_total':70,'remaining':20}]
 t=total_row(r,sum_counts=False);assert t['debtors'] is None and t['expected']==Decimal('190') and t['recovery_rate']==Decimal('78.9')
def test_section_total_can_sum_disjoint_classes():
 r=[{'debtors':20,'in_order':10,'not_in_order':10,'expected':100,'cash_collected':70,'outside_cash':10,'regularized_total':80,'remaining':20},{'debtors':30,'in_order':20,'not_in_order':10,'expected':200,'cash_collected':150,'outside_cash':0,'regularized_total':150,'remaining':50}]
 t=total_row(r,True);assert t['debtors']==50 and t['in_order']==30 and t['not_in_order']==20 and t['expected']==Decimal('300')
def test_register_footer_preserves_original_metrics_and_no_student_rate_column():
 cols=[{'key':'M'}];students=[{'cells':{'M':{'net':100,'paid':60,'advance':0}}},{'cells':{'M':{'net':100,'paid':100,'advance':0}}}]
 f=register_footer(students,cols);assert f['debtors']==2 and f['in_order']==1 and f['not_in_order']==1 and f['recovery_rate']==Decimal('80.0')
def test_frontend_has_all_three_summaries_and_register_footer():
 from pathlib import Path
 s=(Path(__file__).resolve().parents[2]/'frontend/src/recovery.tsx').read_text()
 assert "setSub('class')" in s and "setSub('section')" in s and "setSub('school')" in s
 assert 'Élèves redevables' in s and '<tfoot>' in s
