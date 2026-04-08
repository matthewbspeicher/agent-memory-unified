FROM node:20-alpine AS build

WORKDIR /app

# Copy package files
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm ci

# Copy application code
COPY . /app

# Build the application with env vars for Vite
ARG VITE_TRADING_API_URL
ARG VITE_TRADING_API_KEY
ENV VITE_TRADING_API_URL=$VITE_TRADING_API_URL
ENV VITE_TRADING_API_KEY=$VITE_TRADING_API_KEY
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
