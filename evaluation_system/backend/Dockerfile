FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir --requirement requirements.txt \
    && groupadd --gid 10001 eval \
    && useradd --uid 10001 --gid eval --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin eval

COPY --chown=10001:10001 app/ ./app/
COPY --chown=10001:10001 alembic/ ./alembic/
COPY --chown=10001:10001 scripts/ ./scripts/
COPY --chown=10001:10001 alembic.ini ./alembic.ini

USER 10001:10001

EXPOSE 8090

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
