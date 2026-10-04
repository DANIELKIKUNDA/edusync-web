from edusync.modules.effectifs.domain.models import FGT,HeadcountRow,MaterialDeposit,total_headcount,row_from_mapping
from decimal import Decimal
import pytest


def test_fgt_preserves_total_even_with_historic_unknown_sex():
    x=FGT.from_genders(['F','M',None])
    assert (x.female,x.male,x.total)==(1,1,3)


def test_total_general_adds_all_four_certified_groups():
    rows=[
      HeadcountRow('Primaire','1re primaire','P1',FGT(10,9,19),FGT(1,0,1),FGT(0,1,1),FGT(9,8,17)),
      HeadcountRow('Primaire','2e primaire','P2',FGT(8,7,15),FGT(0,1,1),FGT(1,0,1),FGT(7,6,13)),
    ]
    t=total_headcount(rows)
    assert t.label=='Total général'
    assert t.enrolled==FGT(18,16,34)
    assert t.active==FGT(16,14,30)


def test_mapping_uses_f_g_t_contract():
    r=row_from_mapping({'section_label':'Secondaire','label':'4e Sciences','code':'4SC','enrolled_f':12,'enrolled_m':10,'enrolled_t':22,'abandoned_f':1,'abandoned_m':0,'abandoned_t':1,'transferred_f':0,'transferred_m':1,'transferred_t':1,'active_f':11,'active_m':9,'active_t':20})
    assert r.enrolled.total==22 and r.transferred.male==1 and r.active.female==11


def test_material_deposit_rejects_non_positive_quantity():
    with pytest.raises(ValueError):MaterialDeposit(Decimal('0'),'rame')
