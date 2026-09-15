FROM ubuntu:24.04@sha256:224a1869083a311ef3f13648a154ba79832fbef6364d31493642ca03082da254 AS runtime-base

# Use distribution-maintained Python 3.12, including its security backports.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends python3 ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

FROM runtime-base AS dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3-venv \
    && python3 -m venv /opt/venv
COPY requirements.lock /tmp/requirements.lock
WORKDIR /tmp
RUN /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.lock \
    && /opt/venv/bin/python -m pip uninstall -y pip

FROM runtime-base AS application
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/opt/venv/bin:$PATH"
COPY --from=dependencies /opt/venv /opt/venv
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --no-create-home app
COPY --chown=app:app . .
RUN mkdir -p /app/exports && chown app:app /app/exports
USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
