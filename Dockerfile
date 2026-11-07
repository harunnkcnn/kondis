FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
RUN useradd --create-home --uid 1000 kondis

COPY requirements.txt requirements-postgres.txt ./
RUN pip install -r requirements-postgres.txt

COPY --chown=kondis:kondis . .
RUN KONDIS_SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && mkdir -p /app/data && chown kondis:kondis /app/data

USER kondis
EXPOSE 8000
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz/').status==200 else 1)"

CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers ${WEB_CONCURRENCY:-2} --access-logfile -"]
