from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True,slots=True)
class DeliveryReadiness:
    enabled: bool; channel_enabled: bool; provider_configured: bool; sender_configured: bool; destination_valid: bool
    @property
    def ready(self)->bool:return all((self.enabled,self.channel_enabled,self.provider_configured,self.sender_configured,self.destination_valid))

def sms_segments(text:str)->int:
    # Conservative GSM-ish estimate: Unicode is more expensive. Provider remains authoritative.
    gsm=all(ord(c)<128 for c in text)
    one,multi=(160,153) if gsm else (70,67)
    n=len(text)
    return 1 if n<=one else (n+multi-1)//multi
