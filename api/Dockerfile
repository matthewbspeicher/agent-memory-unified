# Stage 1: Install PHP dependencies
FROM composer:latest AS vendor
# Install redis extension before composer install (required by shared-events package)
RUN apk add --no-cache autoconf g++ make && \
    pecl install redis && \
    docker-php-ext-enable redis && \
    docker-php-ext-install bcmath && \
    apk del autoconf g++ make

WORKDIR /build

# Copy entire monorepo structure to preserve relative paths
COPY shared ./shared
COPY api ./api

# Install composer dependencies from api directory
WORKDIR /build/api
RUN composer install --no-dev --optimize-autoloader --no-scripts

# Stage 2: Build frontend assets
FROM node:20-alpine AS node-build
WORKDIR /build/api
COPY api/package.json api/package-lock.json* ./
RUN NODE_OPTIONS="--max-old-space-size=512" npm ci
COPY api ./
# Copy vendor from Stage 1 so Tailwind v4 can find Laravel's pagination blades
COPY --from=vendor /build/api/vendor ./vendor
RUN npm run build

# Stage 3: PHP application
FROM php:8.3-cli

# Install system deps required by extensions and FrankenPHP
RUN apt-get update && apt-get install -y \
    libpq-dev \
    libzip-dev \
    unzip \
    libcap2-bin \
    && pecl install redis \
    && docker-php-ext-enable redis \
    && docker-php-ext-install pdo_pgsql pgsql zip pcntl opcache bcmath \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy PHP dependencies from vendor stage
COPY --from=vendor /build/api/vendor ./vendor

# Copy application
COPY api ./

# Copy built assets from node stage
COPY --from=node-build /build/api/public/build ./public/build

# Run post-install scripts
RUN php artisan package:discover --ansi \
    && php artisan octane:install --server=frankenphp -n \
    && setcap CAP_NET_BIND_SERVICE=+eip /app/frankenphp

# Create storage dirs
RUN mkdir -p storage/logs \
    storage/framework/cache/data \
    storage/framework/sessions \
    storage/framework/views \
    bootstrap/cache \
    && chmod -R 775 storage bootstrap/cache

RUN cp docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh && chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["docker-entrypoint.sh"]
