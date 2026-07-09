FROM python:3.11-slim

WORKDIR /app

# Copiem requirements și instalăm dependințele
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiem întregul cod (structura nouă)
COPY app/ ./app/
COPY data_ingestion/ ./data_ingestion/
COPY config/ ./config/
# Directorul db/ va fi creat la runtime

# Seed-ul se execută la build (pentru a avea date inițiale)
RUN python data_ingestion/seed_demo_data.py

EXPOSE 8000

# Rulează serverul FastAPI
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
