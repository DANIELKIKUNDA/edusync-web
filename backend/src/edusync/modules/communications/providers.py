"""SMS providers behind one neutral port. Business code only knows SmsProvider; the concrete provider
is chosen per school by a code (communication_settings.provider_code) resolved in provider_for().

Status lifecycle (communication_deliveries.status): PENDING -> QUEUED -> SENT -> DELIVERED, or FAILED.
SENT requires a provider message id; DELIVERED requires a provider delivery report (never assumed).
"""
from __future__ import annotations
import hashlib
from dataclasses import dataclass
from typing import Protocol
import httpx


@dataclass(frozen=True)
class DeliveryResult: accepted:bool; provider_message_id:str|None=None; error_code:str|None=None


@dataclass(frozen=True)
class DeliveryReport:
 """Final state reported by the provider for one accepted message."""
 status:str  # DELIVERED | FAILED | PENDING (no final state yet)
 error_code:str|None=None


class SmsProvider(Protocol):
 code:str
 def send_sms(self,*,destination:str,body:str,sender_id:str|None)->DeliveryResult:...
 def delivery_report(self,provider_message_id:str)->DeliveryReport:...


Provider=SmsProvider  # historical name kept for existing callers


class MockProvider:
 """Development/test only (refused in production by provider_for)."""
 code='mock'
 def send_sms(self,*,destination:str,body:str,sender_id:str|None)->DeliveryResult:return DeliveryResult(True,'mock-'+destination[-6:])
 def delivery_report(self,provider_message_id:str)->DeliveryReport:return DeliveryReport('DELIVERED')


class SandboxSmsProvider:
 """Deterministic local sandbox: exercises every path (accept, reject, timeout, delivered, undelivered)
 without any operator. Destinations ending in 0000 are rejected, 9999 time out, 8888 are accepted
 but reported undelivered; everything else is accepted then delivered. Never used in production."""
 code='sandbox'
 def send_sms(self,*,destination:str,body:str,sender_id:str|None)->DeliveryResult:
  digits=''.join(ch for ch in destination if ch.isdigit())
  if len(digits)<9:return DeliveryResult(False,error_code='INVALID_DESTINATION')
  if digits.endswith('0000'):return DeliveryResult(False,error_code='PROVIDER_REJECTED')
  if digits.endswith('9999'):return DeliveryResult(False,error_code='PROVIDER_TIMEOUT')
  mid='sbx-'+hashlib.sha256(f'{destination}|{body}|{sender_id}'.encode()).hexdigest()[:20]
  return DeliveryResult(True,('undeliv-' if digits.endswith('8888') else '')+mid)
 def delivery_report(self,provider_message_id:str)->DeliveryReport:
  return DeliveryReport('FAILED','UNDELIVERABLE') if provider_message_id.startswith('undeliv-') else DeliveryReport('DELIVERED')


class OrangeSmsProvider:
 """Orange/A2P adapter. Endpoint and bearer token are deployment secrets; no hard-coded commercial assumptions."""
 code='orange'
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
 def delivery_report(self,provider_message_id:str)->DeliveryReport:
  # The real operator contract (polling or webhook) is certified in staging; until then no DELIVERED is invented.
  return DeliveryReport('PENDING')


def provider_for(cfg,code:str|None)->SmsProvider|None:
 """Resolve a provider by code. Test providers are refused in production; unknown codes resolve to None
 (deliveries then fail with PROVIDER_NOT_CONFIGURED instead of being reported as sent)."""
 code=(code or '').lower(); prod=cfg.env.lower() in {'prod','production'}
 if code=='mock' and not prod:return MockProvider()
 if code=='sandbox' and not prod:return SandboxSmsProvider()
 if code=='orange':return OrangeSmsProvider(cfg.orange_sms_endpoint,cfg.orange_sms_bearer_token)
 return None
