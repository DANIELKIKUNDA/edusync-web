"""Central NotificationPolicy: the ONLY place deciding which external channel reaches which recipient.
Finance, schooling or cash never decide channels: they emit an event / request with the channels they wish, the
policy filters them against the school settings, the recipient data and the available devices.

  SMS   only if the school enabled SMS, the number is valid E.164 and credits were reserved for the message
  EMAIL only if an address exists and e-mail is enabled for the school (account e-mails: platform e-mail enabled)
  PUSH  only to the recipient's active devices of the same school (platform devices for platform messages), if the
        school did not switch push off
A skipped channel is never an error of the business operation that requested it.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelDecision:
    channel: str
    destination: str | None       # E.164, e-mail address or push subscription id
    send: bool
    reason: str | None = None     # why the channel is skipped (shown in history, never sent to the provider)


def decide(*, channels: list[str], kind: str, settings: dict | None, phone: str | None, email: str | None,
           sms_reserved: bool, push_devices: list[str], seen_phones: set[str] | None = None) -> list[ChannelDecision]:
    s = settings or {}
    school_on = bool(s.get("enabled"))
    account = kind in {"ACCOUNT", "PLATFORM"}
    out: list[ChannelDecision] = []
    for ch in channels:
        if ch == "SMS":
            if account:
                out.append(ChannelDecision("SMS", None, False, "SMS_NOT_FOR_ACCOUNT_MESSAGES"))
            elif not (school_on and s.get("sms_enabled")):
                out.append(ChannelDecision("SMS", phone, False, "SMS_DISABLED_FOR_SCHOOL"))
            elif not phone:
                out.append(ChannelDecision("SMS", None, False, "NO_VALID_PHONE"))
            elif seen_phones is not None and phone in seen_phones:
                out.append(ChannelDecision("SMS", phone, False, "DUPLICATE_PHONE"))
            elif not sms_reserved:
                out.append(ChannelDecision("SMS", phone, False, "NO_SMS_CREDIT_RESERVED"))
            else:
                if seen_phones is not None:
                    seen_phones.add(phone)
                out.append(ChannelDecision("SMS", phone, True))
        elif ch == "EMAIL":
            if not email:
                out.append(ChannelDecision("EMAIL", None, False, "NO_EMAIL_ADDRESS"))
            elif not account and not (school_on and s.get("email_enabled")):
                out.append(ChannelDecision("EMAIL", email, False, "EMAIL_DISABLED_FOR_SCHOOL"))
            else:
                out.append(ChannelDecision("EMAIL", email, True))
        elif ch == "PUSH":
            if not account and s and s.get("push_enabled") is False:
                out.append(ChannelDecision("PUSH", None, False, "PUSH_DISABLED_FOR_SCHOOL"))
            elif not push_devices:
                out.append(ChannelDecision("PUSH", None, False, "NO_PUSH_DEVICE"))
            else:
                out.extend(ChannelDecision("PUSH", device, True) for device in push_devices)
    return out
