FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build
COPY requirements.txt .
RUN python -m pip wheel --wheel-dir /wheels -r requirements.txt

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

RUN groupadd --gid 10001 socialite \
    && useradd --uid 10001 --gid socialite --create-home --shell /usr/sbin/nologin socialite

WORKDIR /app
COPY --from=builder /wheels /wheels
COPY requirements.txt .
RUN python -m pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

COPY --chown=socialite:socialite . .

USER socialite
EXPOSE 8000
STOPSIGNAL SIGTERM

CMD ["gunicorn", "--config", "gunicorn.conf.py", "wsgi:application"]
