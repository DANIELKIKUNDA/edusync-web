import sys; sys.path.insert(0, __import__('os').path.dirname(__file__))
from common import *
for n in ('A','B'):
    s=ensure_school(n,())
    ensure_user(s,'ADMIN',('GESTIONNAIRE','SECRETARIAT','RESPONSABLE_FINANCE'))
    c=user_client(s,'ADMIN')
    for p in ['auth/me','settings/sections','settings/academic-years','settings/classes','settings/fee-types']:
        r=call(c,'GET',p); print(n,p,r.status_code,r.text[:400])
