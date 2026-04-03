#!/bin/bash
# scripts/dev-setup.sh
set -e

echo "🚀 Setting up agent-memory development environment..."

# Generate types
echo "1️⃣  Generating shared types..."
./scripts/sync-types.sh

# Install Python dependencies
echo "2️⃣  Installing Python dependencies..."
cd trading
pip install -e .
cd ..

# Install PHP dependencies
echo "3️⃣  Installing PHP dependencies..."
cd api
composer install
cd ..

# Install frontend dependencies
echo "4️⃣  Installing frontend dependencies..."
cd frontend
npm install
cd ..

# Start Docker services
echo "5️⃣  Starting Docker services..."
docker-compose up -d postgres redis

# Wait for Postgres
echo "⏳ Waiting for Postgres..."
until docker-compose exec -T postgres pg_isready; do
  sleep 1
done

# Run Laravel migrations
echo "6️⃣  Running database migrations..."
cd api
php artisan migrate
cd ..

echo "✅ Development environment ready!"
echo ""
echo "Start services:"
echo "  API:      cd api && php artisan serve"
echo "  Trading:  cd trading && uvicorn api.main:app --reload"
echo "  Frontend: cd frontend && npm run dev"
