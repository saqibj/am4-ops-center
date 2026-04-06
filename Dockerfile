# ── Stage 1: build am4 C++ extension and Python deps ─────────────────────────
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.in requirements.lock ./
COPY scripts/strip_vcs_from_lock.py ./scripts/
# am4 is a VCS direct dep: pip cannot hash it; install from requirements.in first, then hashed PyPI pins.
RUN pip install --no-cache-dir --upgrade pip \
    && AM4_LINE=$(python3 -c "import pathlib,re; t=pathlib.Path('requirements.in').read_text(encoding='utf-8'); m=re.search(r'^am4 @.+$', t, re.M); assert m, 'am4 line not in requirements.in'; print(m.group(0).strip())") \
    && pip install --no-cache-dir "$AM4_LINE" \
    && python3 scripts/strip_vcs_from_lock.py requirements.lock /tmp/requirements-hashed.lock \
    && pip install --no-cache-dir --require-hashes -r /tmp/requirements-hashed.lock

# ── Stage 2: runtime (no compilers) ──────────────────────────────────────────
FROM python:3.12-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 1000 appuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

COPY --chown=appuser:appuser . .

RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

USER appuser

EXPOSE 8000

# Bridge networking needs 0.0.0.0; bind host port to 127.0.0.1 in compose for local-only access.
CMD ["python", "main.py", "dashboard", "--host", "0.0.0.0", "--db", "/app/data/am4_data.db"]
