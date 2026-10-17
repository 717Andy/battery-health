# Hugging Face Spaces (Docker SDK) and local demo image.
# Serves the FastAPI UI on port 7860 using shipped ONNX + bundled fixtures.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/ml \
    HOST=0.0.0.0 \
    PORT=7860

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY ml/requirements-space.txt ml/requirements-space.txt
RUN pip install --no-cache-dir -r ml/requirements-space.txt

COPY ml/ ml/
COPY artifacts/ artifacts/
COPY tests/fixtures/ tests/fixtures/

EXPOSE 7860

CMD ["python", "-m", "batteryhealth.service.app", "--host", "0.0.0.0", "--port", "7860"]
