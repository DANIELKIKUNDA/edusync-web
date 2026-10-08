from __future__ import annotations
import json, logging
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
try:
    import structlog  # production structured logger
except ImportError:  # local certification can run before dependency installation
    structlog=None

def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    if structlog:
        structlog.configure(processors=[structlog.contextvars.merge_contextvars,structlog.processors.TimeStamper(fmt='iso',utc=True),structlog.processors.add_log_level,structlog.processors.JSONRenderer()])

def _log(event:str,**fields):
    if structlog:
        structlog.get_logger('edusync').info(event,**fields)
    else:
        logging.getLogger('edusync').info(json.dumps({'ts':datetime.now(timezone.utc).isoformat(),'event':event,**fields},ensure_ascii=False))

class CorrelationLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        correlation_id=request.headers.get('X-Correlation-ID') or str(uuid4())
        try:
            response=await call_next(request)
            response.headers['X-Correlation-ID']=correlation_id
            _log('http_request',correlation_id=correlation_id,path=request.url.path,method=request.method,status=response.status_code)
            if response.status_code>=500:
                _count_server_error(request)
            return response
        except Exception as exc:
            logging.getLogger('edusync').exception(json.dumps({'event':'http_unhandled_error','correlation_id':correlation_id,'path':request.url.path,'method':request.method,'error_type':type(exc).__name__}))
            _count_server_error(request)
            raise


def _count_server_error(request: Request) -> None:
    """Hourly 5xx counter for the health screen (no path parameters, no user, no payload)."""
    try:
        state=request.app.state
        r=getattr(state,'_errors_redis',None)
        if r is None:
            import redis
            r=redis.Redis.from_url(state.services.settings.redis_url,socket_connect_timeout=.5,socket_timeout=.5)
            state._errors_redis=r
        from edusync.shared.infrastructure.heartbeat import record_server_error
        record_server_error(r)
    except Exception:  # noqa: BLE001 — observability never breaks a response
        pass
