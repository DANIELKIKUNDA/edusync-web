from __future__ import annotations
import asyncio, json, logging, time
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import Request
from fastapi.responses import JSONResponse
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
        request.state.correlation_id=correlation_id
        t0=time.perf_counter()
        try:
            response=await call_next(request)
            response.headers['X-Correlation-ID']=correlation_id
            _log('http_request',correlation_id=correlation_id,path=request.url.path,method=request.method,status=response.status_code)
            _record(request,response.status_code,t0,correlation_id,getattr(request.state,'error_type',None),getattr(request.state,'error_message',''))
            return response
        except Exception as exc:
            logging.getLogger('edusync').exception(json.dumps({'event':'http_unhandled_error','correlation_id':correlation_id,'path':request.url.path,'method':request.method,'error_type':type(exc).__name__}))
            _record(request,500,t0,correlation_id,type(exc).__name__,str(exc))
            # A clean answer carrying the reference (support can find the group and the log line), never a trace.
            return JSONResponse(status_code=500,headers={'X-Correlation-ID':correlation_id},
                                content={'detail':f'Une erreur inattendue est survenue. Référence : {correlation_id[:8]}','correlation_id':correlation_id})


def _route_template(request: Request) -> str:
    """The matched route template (/platform/schools/{school_id}), never the concrete path: no identifier is kept."""
    route=request.scope.get('route')
    path=getattr(route,'path',None)
    return path if isinstance(path,str) else 'route inconnue'


def _redis(request: Request):
    state=request.app.state
    r=getattr(state,'_signals_redis',None)
    if r is None:
        import redis
        r=redis.Redis.from_url(state.services.settings.redis_url,socket_connect_timeout=.5,socket_timeout=.5)
        state._signals_redis=r
    return r


def _record(request: Request, status: int, t0: float, correlation_id: str, error_type: str | None, message: str) -> None:
    """Golden signals + grouped 5xx (signals.py), handed to a thread: never delays nor breaks the response."""
    if not request.url.path.startswith('/api/'):
        return
    try:
        from edusync.shared.infrastructure.signals import record_request
        r=_redis(request)
        kwargs=dict(method=request.method,route=_route_template(request),status=int(status),duration_ms=int((time.perf_counter()-t0)*1000),
                    correlation_id=correlation_id,error_type=error_type,message=message or '')
        asyncio.get_running_loop().run_in_executor(None,lambda:record_request(r,**kwargs))
    except Exception:  # noqa: BLE001 — observability never breaks a response
        pass
