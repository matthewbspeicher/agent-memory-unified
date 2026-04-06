FROM python:3.13-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml ./
RUN pip install -e .

# Copy application code
COPY . .

# Start command (use shell form to allow $PORT expansion)
CMD python3 -m uvicorn api.app:app --host 0.0.0.0 --port $PORT
