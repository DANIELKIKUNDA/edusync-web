from __future__ import annotations
import re
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


# Templates: schools write their own wording; EduSync only substitutes declared variables.
TEMPLATE_VARIABLES=frozenset({'ecole','eleve','classe','responsable','montant','devise','reste','date','recu'})
_PLACEHOLDER=re.compile(r'\{\{\s*([a-z_]+)\s*\}\}')

def template_variables(body:str)->set[str]:
    return set(_PLACEHOLDER.findall(body or ''))

def validate_template(body:str)->None:
    unknown=template_variables(body)-TEMPLATE_VARIABLES
    if unknown:raise ValueError('Variables inconnues : '+', '.join(sorted(unknown)))
    if not (body or '').strip():raise ValueError('Le modèle est vide.')

def render_template(body:str,values:dict[str,object])->str:
    """Strict rendering: unknown or missing variables are errors, never sent as '{{...}}' to a parent."""
    validate_template(body)
    missing=[v for v in template_variables(body) if values.get(v) in (None,'')]
    if missing:raise ValueError('Valeurs manquantes : '+', '.join(sorted(missing)))
    return _PLACEHOLDER.sub(lambda m:str(values[m.group(1)]).replace('\r',' ').replace('\n',' '),body)
