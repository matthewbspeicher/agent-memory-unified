FROM node:20-alpine AS build

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci

# Create .env file for build (Railway passes these as build args)
RUN echo "VITE_TRADING_API_URL=${VITE_TRADING_API_URL:-http://localhost:8080}" > .env.production && \
    echo "VITE_TRADING_API_KEY=${VITE_TRADING_API_KEY:-local-validator-dev}" >> .env.production

# Copy application code
COPY . /app

# Build the application (Vite reads .env.production)
RUN npm run build

# Production stage
FROM node:20-alpine

WORKDIR /app

# Install serve globally
RUN npm install -g serve

# Copy built assets from build stage
COPY --from=build /app/dist ./dist

# Start command (use shell form to allow $PORT expansion)
CMD serve -s dist -l $PORT
