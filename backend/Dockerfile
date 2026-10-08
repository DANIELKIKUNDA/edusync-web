FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
# Exact versions of the certified environment (supply chain: reproducible clean-clone build).
RUN pip install --no-cache-dir -c requirements.lock .
COPY migrations ./migrations
COPY scripts ./scripts
ENV PYTHONPATH=/app/src
# Behind nginx: real client IPs come from X-Forwarded-For, trusted only from FORWARDED_ALLOW_IPS
# (set by docker-compose). Without this every user shares the proxy IP and the per-IP login throttle
# becomes a platform-wide lockout. --no-server-header avoids disclosing the server stack.
CMD ["uvicorn", "edusync.bootstrap.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--no-server-header"]
