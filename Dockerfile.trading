FROM python:3.13-slim

# Install build dependencies for hnswlib and other compiled packages
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy shared directory (auth, types-py, etc.)
COPY shared /app/shared

# Copy shared types package (required dependency)
COPY shared/types-py /app/shared-types

# Copy trading service
COPY trading /app/trading

# Install shared-types first, then trading package
RUN pip install -e /app/shared-types && \
    pip install -e /app/trading

# Set PYTHONPATH to include /app so 'import shared' works
ENV PYTHONPATH=/app:$PYTHONPATH

# Copy the entrypoint script
COPY trading/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Set working directory to trading service
WORKDIR /app/trading

# Start command via entrypoint
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python3", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
