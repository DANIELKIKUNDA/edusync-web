from __future__ import annotations
import hashlib,secrets
from dataclasses import dataclass

def new_session_token()->tuple[str,str]:
 raw=secrets.token_urlsafe(48); return raw,hash_token(raw)
def hash_token(raw:str)->str:return hashlib.sha256(raw.encode()).hexdigest()
def hash_user_agent(value:str)->str:return hashlib.sha256((value or '').encode()).hexdigest()
def describe_user_agent(value:str)->str:
 """Readable device label for the user's session list (browser · system); the raw string is never stored."""
 ua=(value or '').lower()
 browser=next((n for k,n in (('edg/','Edge'),('opr/','Opera'),('samsungbrowser','Samsung Internet'),('firefox/','Firefox'),('chrome/','Chrome'),('safari/','Safari')) if k in ua),'Navigateur')
 system=next((n for k,n in (('android','Android'),('iphone','iPhone'),('ipad','iPad'),('windows','Windows'),('mac os','macOS'),('linux','Linux')) if k in ua),'')
 return f'{browser} · {system}' if system else browser
