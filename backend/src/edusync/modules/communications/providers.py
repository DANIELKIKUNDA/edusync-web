from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
import httpx
@dataclass(frozen=True)
class DeliveryResult: accepted:bool; provider_message_id:str|None=None; error_code:str|None=None
class Provider(Protocol):
 def send_sms(self,*,destination:str,body:str,sender_id:str|None)->DeliveryResult:...
class MockProvider:
 def send_sms(self,*,destination:str,body:str,sender_id:str|None)->DeliveryResult:return DeliveryResult(True,'mock-'+destination[-6:])
class OrangeSmsProvider:
 """Orange/A2P adapter. Endpoint and bearer token are deployment secrets; no hard-coded commercial assumptions."""
 def __init__(self,endpoint:str,bearer_token:str,timeout_seconds:float=12):self.endpoint=endpoint;self.token=bearer_token;self.timeout=timeout_seconds
 def send_sms(self,*,destination:str,body:str,sender_id:str|None)->DeliveryResult:
  if not self.endpoint or not self.token:return DeliveryResult(False,error_code='PROVIDER_NOT_CONFIGURED')
  try:
   r=httpx.post(self.endpoint,headers={'Authorization':f'Bearer {self.token}','Content-Type':'application/json'},json={'to':destination,'message':body,'sender':sender_id},timeout=self.timeout)
   if 200<=r.status_code<300:
    data=r.json() if r.content else {};return DeliveryResult(True,str(data.get('messageId') or data.get('id') or '') or None)
   return DeliveryResult(False,error_code=f'PROVIDER_HTTP_{r.status_code}')
  except httpx.TimeoutException:return DeliveryResult(False,error_code='PROVIDER_TIMEOUT')
  except httpx.HTTPError:return DeliveryResult(False,error_code='PROVIDER_NETWORK')
