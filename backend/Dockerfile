FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NETMEDIC_HOST=0.0.0.0 \
    NETMEDIC_PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY pytest.ini .
RUN mkdir -p data/models

EXPOSE 8000

# The Isolation Forest is trained on first boot if no model artefact exists (10-20 s depending on the host).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
