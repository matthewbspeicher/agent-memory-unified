# Stage 1: Install PHP dependencies
FROM composer:latest AS vendor
RUN docker-php-ext-install bcmath
WORKDIR /app
COPY composer.json composer.lock ./
RUN composer install --no-dev --optimize-autoloader --no-scripts

# Stage 2: Build frontend assets
FROM node:20-alpine AS node-build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN NODE_OPTIONS="--max-old-space-size=512" npm ci
COPY . .
# Copy vendor from Stage 1 so Tailwind v4 can find Laravel's pagination blades
COPY --from=vendor /app/vendor ./vendor
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
COPY --from=vendor /app/vendor ./vendor

# Copy application
COPY . .

# Copy built assets from node stage
COPY --from=node-build /app/public/build ./public/build

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

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8080

ENTRYPOINT ["docker-entrypoint.sh"]
