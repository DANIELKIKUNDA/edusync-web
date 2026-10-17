"""Compatibility entry point. The SMS providers now live behind SmsProviderPort in edusync.shared.messaging
(Orange adapter written from the official Orange Developer documentation, fakes for development only).

provider_for(cfg, code) keeps its historical contract: simulated providers are refused in every protected environment
(staging, production) and unknown codes resolve to None, so deliveries fail with PROVIDER_NOT_CONFIGURED instead of
being reported as sent.
"""
from __future__ import annotations

from types import SimpleNamespace

from edusync.bootstrap.settings import is_protected_env
from edusync.shared.messaging.factory import build_sms_provider


def provider_for(cfg, code: str | None):
    code = (code or '').strip().lower()
    if code in {'mock', 'sandbox', 'fake'} and is_protected_env(cfg.env):
        return None
    if code not in {'mock', 'sandbox', 'fake', 'orange'}:
        return None
    kind = 'fake' if code in {'mock', 'sandbox'} else code
    view = cfg.model_copy(update={'sms_provider': kind}) if hasattr(cfg, 'model_copy') else SimpleNamespace(**{**vars(cfg), 'sms_provider': kind})
    return build_sms_provider(view)
