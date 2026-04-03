#!/bin/bash
set -e

echo "Running migrations..."
php artisan migrate --force

echo "Caching config..."
php artisan config:clear
php artisan config:cache
php artisan route:cache
php artisan view:cache

echo "Linking storage..."
php artisan storage:link 2>/dev/null || true

echo "Deploy complete."
