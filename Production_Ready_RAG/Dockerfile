# ==================================================================
# Ejadah HR AI Assistant
# ==================================================================
#
# Two stages so the ~2GB of build tooling that torch and
# sentence-transformers pull in does not ship to production.
#
# The embedding model is downloaded at BUILD time. Otherwise the
# first employee to ask a question waits for a 90MB download, and a
# production host with no egress to huggingface.co never starts.
# ==================================================================

FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# Warm the sentence-transformer cache.
ENV HF_HOME=/opt/hf
RUN /opt/venv/bin/python -c \
    "from sentence_transformers import SentenceTransformer; \
     SentenceTransformer('all-MiniLM-L6-v2')"


# ------------------------------------------------------------------

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/opt/hf \
    TRANSFORMERS_OFFLINE=1

# Runs as a non-root user: the process only needs to read its code
# and write to data/ and logs/.
RUN groupadd --system app \
 && useradd --system --gid app --home /app app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/hf /opt/hf

COPY --chown=app:app . /app

# .env is mounted or injected at run time, never baked in.
RUN rm -f /app/.env \
 && mkdir -p /app/data /app/logs \
 && chown -R app:app /app/data /app/logs /opt/hf

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request,sys; \
sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status==200 else sys.exit(1)"

# No --log-config here. api.main calls configure_logging() at import
# time, which installs our formatter and the token-redacting filter
# on the root logger; handing uvicorn a config file as well just
# fights with it. (And `--log-config /dev/null` does not work -
# uvicorn tries to parse the path as a config file.)
#
# --no-access-log because the app logs one line per request itself,
# with the employee id attached and the query string omitted.
CMD ["uvicorn", "api.main:socket_app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*", \
     "--no-access-log"]
