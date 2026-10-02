# Isnad main website — runtime image
# Python version is pinned explicitly so it does not change on Railway rebuilds.
FROM python:3.11.9-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies get their own layer so the cache is reused unless requirements.txt changes.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Run as an unprivileged user: a flaw in the app can't then modify the image or the system.
RUN useradd --create-home --uid 10001 isnad
COPY --chown=isnad:isnad . .
USER isnad

EXPOSE 8000

# --proxy-headers: trust Railway's proxy so rate limits see the real visitor IP
# and the visitor cookie is marked Secure over HTTPS.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
