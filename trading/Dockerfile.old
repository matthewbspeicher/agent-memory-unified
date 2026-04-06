FROM stock-trading-api-base:latest

WORKDIR /app

# Application code
COPY . .

# Ensure db-data directory exists for volume mount (separate from /app/data Python package)
RUN mkdir -p /app/db-data

CMD ["python", "main.py"]
