FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY ui.html .

# ── Production URL ────────────────────────────────────────────────────────────
# IBM Code Engine injects PORT at runtime; the APP_URL is the public HTTPS URL
# used for CORS and for the /health endpoint's self-reference.
# Override at build time: docker build --build-arg APP_URL=https://... .
# In Code Engine set APP_URL as an environment variable in the application config.
ARG APP_URL=https://cda-app.2d591frd9jfp.eu-de.codeengine.appdomain.cloud
ENV APP_URL=${APP_URL}

# PORT is injected by Code Engine at runtime; default matches local dev
ENV PORT=8080

EXPOSE 8080

# 2 workers is appropriate for the Code Engine 0.5 vCPU / 1 GB tier.
# Increase to 4 for the 1 vCPU tier.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--timeout", "60", "app:app"]
