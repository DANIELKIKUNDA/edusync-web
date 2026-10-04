from __future__ import annotations
import hashlib,secrets
from dataclasses import dataclass

def new_session_token()->tuple[str,str]:
 raw=secrets.token_urlsafe(48); return raw,hash_token(raw)
def hash_token(raw:str)->str:return hashlib.sha256(raw.encode()).hexdigest()
def hash_user_agent(value:str)->str:return hashlib.sha256((value or '').encode()).hexdigest()
