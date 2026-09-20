FROM python:3.11-slim-bookworm

ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TOKENIZERS_PARALLELISM=false

RUN groupadd --gid "${APP_GID}" llm-studio \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --no-create-home --shell /usr/sbin/nologin llm-studio

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement /app/requirements.txt

COPY --chown=${APP_UID}:${APP_GID} api /app/api

USER ${APP_UID}:${APP_GID}

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log", "--timeout-keep-alive", "5", "--limit-concurrency", "16", "--h11-max-incomplete-event-size", "65536", "--proxy-headers", "--forwarded-allow-ips", ""]
