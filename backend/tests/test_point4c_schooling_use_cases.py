from uuid import uuid4
import pytest
from edusync.modules.schooling.application.use_cases import SchoolingService

class FakeRepo:
    def __init__(self, policy=None):
        self.school=uuid4(); self.year=uuid4(); self.cls=uuid4(); self.family=None; self.students=[]; self.enrollments=[]; self.guardians=[]; self.benefits=[]; self.policy=policy or {"required_student_fields":["last_name","middle_name","first_name","gender","class_id"],"guardian_required_at_enrollment":False,"guardian_phone_required":False}; self.n=0
    def active_year(self,sid): return {'id':self.year}
    def enrollment_policy(self,sid): return self.policy
    def class_info(self,sid,cid): return {'id':self.cls,'academic_year_id':self.year,'active':True,'section_code':'SECONDAIRE','code':'3HP'} if cid==self.cls else None
    def get_student_unscoped(self,*a): return None
    def get_family(self,sid,fid): return self.family if self.family and self.family['id']==fid else None
    def next_code(self,sid,ns,prefix): self.n+=1; return f'{prefix}-{self.n:05d}'
    def create_family(self,obj): self.family={'id':obj.id,'display_name':obj.display_name,'code':obj.code}; return self.family
    def create_guardian(self,obj): self.guardians.append(obj); return {'id':obj.id}
    def link_guardian(self,*a,**kw): return kw
    def record_household_resolution(self,*a,**kw): pass
    def create_student(self,obj): self.students.append(obj); return {'id':obj.id}
    def create_enrollment(self,obj): self.enrollments.append(obj); return {'id':obj.id}
    def link_staff_child(self,*a,**kw): pass
    def add_benefit(self,obj): self.benefits.append(obj); return {'id':obj.id}
    def count_family_enrolled_children(self,*a): return len(self.students)

def service(repo, scopes=(("SCHOOL",None),)):
    return SchoolingService(repo,school_id=repo.school,actor_user_id=uuid4(),permitted_scopes=scopes)

def child(repo, **overrides):
    x=dict(last_name='KIKUNDA',middle_name='NGWEJ',first_name='Daniel',gender='M',class_id=repo.cls,birth_date=None,birth_place=None)
    x.update(overrides); return x

def test_default_terrain_policy_allows_unknown_birth_data_and_no_guardian():
    r=FakeRepo(); out=service(r).enroll_family_batch(children=[child(r)])
    assert out['count']==1
    assert r.family['display_name']=='Foyer KIKUNDA NGWEJ Daniel'
    assert r.guardians==[]

def test_school_can_explicitly_require_birth_date_without_changing_global_default():
    r=FakeRepo({"required_student_fields":["last_name","middle_name","first_name","gender","class_id","birth_date"],"guardian_required_at_enrollment":False,"guardian_phone_required":False})
    with pytest.raises(ValueError,match='date de naissance obligatoire'):
        service(r).enroll_family_batch(children=[child(r)])

def test_primary_guardian_generates_family_label_and_is_distinct_entity():
    r=FakeRepo(); out=service(r).enroll_family_batch(children=[child(r)],primary_guardian={'full_name':'Espérance Ilunga','phone':'+243990000000','role':'MERE','is_primary':True})
    assert r.family['display_name']=='Foyer de Espérance Ilunga'
    assert len(r.guardians)==1
    assert str(r.guardians[0].id) != out['family_id']

def test_enrollment_scope_is_enforced_per_target_class():
    r=FakeRepo()
    with pytest.raises(PermissionError,match='hors de votre périmètre'):
        service(r,scopes=(("SECTION","PRIMAIRE"),)).enroll_family_batch(children=[child(r)])
