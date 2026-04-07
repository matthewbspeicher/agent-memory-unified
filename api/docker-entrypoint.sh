#!/bin/bash
set -e

echo "[entrypoint] Starting application..."

# Run migrations FIRST (must happen before any cache commands on fresh DB)
echo "[entrypoint] Running migrations..."
php artisan migrate --force 2>&1 || echo "[entrypoint] WARNING: Migration failed, continuing anyway"

echo "[entrypoint] Seeding Arena gyms..."
php artisan db:seed --class=ArenaGymSeeder --force 2>&1 || echo "[entrypoint] WARNING: Arena Seeding failed"

# Now safe to clear and rebuild caches (tables exist after migration)
echo "[entrypoint] Clearing stale caches..."
php artisan optimize:clear 2>&1 || echo "[entrypoint] WARNING: optimize:clear failed, continuing"

echo "[entrypoint] Caching config..."
php artisan config:cache 2>&1 || echo "[entrypoint] WARNING: Config cache failed"
php artisan route:cache 2>&1 || echo "[entrypoint] WARNING: Route cache failed"
php artisan view:cache 2>&1 || echo "[entrypoint] WARNING: View cache failed"

# Create storage link if not exists
php artisan storage:link 2>/dev/null || true

# Start background processes for production (webhooks & cleanup)
echo "[entrypoint] Starting background queue worker..."
php artisan queue:work --tries=3 --timeout=90 &

echo "[entrypoint] Starting background scheduler..."
php artisan schedule:work &

# Start the server — use PORT from Railway, default 8080
PORT="${PORT:-8080}"
echo "[entrypoint] Starting server on port $PORT using Octane (FrankenPHP)"
exec php artisan octane:start --server=frankenphp --host=0.0.0.0 --port="$PORT"
