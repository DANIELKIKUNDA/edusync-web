from __future__ import annotations
import hashlib, time
from dataclasses import dataclass

@dataclass(frozen=True)
class LoginDecision:
    allowed: bool
    retry_after: int = 0

class LoginAttemptGuard:
    """Distributed login throttling. Never stores raw email/IP in Redis keys."""
    def __init__(self, redis_url: str, *, window_seconds: int=900, max_attempts: int=7, lock_seconds: int=900, namespace: str="auth"):
        # Separate counters per concern: second-factor failures ("mfa") never share the password counters ("auth").
        self.namespace=namespace
        try:
            from redis import Redis
            self.redis=Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=0.35, socket_timeout=0.35)
        except Exception:
            self.redis=None
        self.window=window_seconds; self.max=max_attempts; self.lock=lock_seconds
        # A whole school often shares one public address (NAT): the per-address threshold is much higher than the
        # per-account one, so a few typing errors by colleagues never lock the school out (N1 2026-10).
        self.max_ip=max(50, max_attempts*7)
    @staticmethod
    def _digest(value:str)->str:
        return hashlib.sha256(value.strip().lower().encode()).hexdigest()[:32]
    def _keys(self,email:str,ip:str):
        ns=getattr(self,"namespace","auth")
        return (f"edusync:{ns}:fail:acct:{self._digest(email)}", f"edusync:{ns}:fail:ip:{self._digest(ip)}")
    def check(self,email:str,ip:str)->LoginDecision:
        try:
            if self.redis is None: return LoginDecision(True,0)
            ttls=[]
            for k,limit in zip(self._keys(email,ip),(self.max,self.max_ip)):
                n=int(self.redis.get(k) or 0)
                if n>=limit: ttls.append(max(self.redis.ttl(k),1))
            return LoginDecision(not ttls, max(ttls) if ttls else 0)
        except Exception:
            # Availability-safe: authentication still verifies Argon2; edge/proxy rate limiting remains recommended.
            return LoginDecision(True,0)
    def failure(self,email:str,ip:str)->None:
        try:
            if self.redis is None: return
            for k,limit in zip(self._keys(email,ip),(self.max,self.max_ip)):
                pipe=self.redis.pipeline(); pipe.incr(k); pipe.ttl(k); n,ttl=pipe.execute()
                if ttl < 0: self.redis.expire(k,self.window)
                if int(n)>=limit: self.redis.expire(k,self.lock)
        except Exception: pass
    def success(self,email:str,ip:str)->None:
        try:
            if self.redis is None: return
            # Only the account counter is cleared: a valid login on an attacker-owned account
            # must not reset the per-IP counter used against other accounts.
            self.redis.delete(self._keys(email,ip)[0])
        except Exception: pass
