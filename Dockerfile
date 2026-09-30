# Single image shared by both app instances (prod_preprod, preprod_dev).
# Which instance a given container runs is decided entirely by the CMD/args
# set in the corresponding k8s Deployment - see k8s/deployment-*.yaml.
FROM python:3.12-slim

RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY config_data/ ./config_data/
COPY run_prod_preprod.py run_preprod_dev.py ./

RUN mkdir -p /app/instance && chown -R appuser:appuser /app
USER appuser

# Actual port is selected per-Deployment via the PORT env var + matching
# containerPort/service; both are declared here for documentation purposes.
EXPOSE 5001 5002

# Default command runs the prod->preprod console with a production WSGI
# server. The preprod->dev Deployment overrides this (see k8s manifests).
CMD ["gunicorn", "--bind", "0.0.0.0:5001", "--workers", "4", "--timeout", "120", "run_prod_preprod:app"]
