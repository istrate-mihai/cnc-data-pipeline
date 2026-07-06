FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pandas matplotlib

COPY spc_analysis.py api.py seed_demo_data.py ./

# Render free tier has no persistent process for a separate Modbus
# simulator, so we seed a demo dataset at build/start time. This is a
# deliberate simplification for the "public URL to click and see it work"
# use case -- data_logger.py + modbus_server.py remain the real pipeline
# to run locally/on your own machine when demonstrating live ingestion.
RUN python3 seed_demo_data.py

EXPOSE 8000
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
