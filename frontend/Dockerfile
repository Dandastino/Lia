# Build stage
FROM node:18-alpine as builder

WORKDIR /app

# Accept build argument for API URL
ARG VITE_API_URL=http://backend:5000

COPY frontend/package*.json .

RUN npm install --legacy-peer-deps

COPY frontend/ .

# Build with API URL environment variable
RUN VITE_API_URL=${VITE_API_URL} npm run build

# Production stage
FROM node:18-alpine

WORKDIR /app

# Install serve to run the app
RUN npm install -g serve

# Copy built app from builder
COPY --from=builder /app/dist ./dist

# Create non-root user (use different UID/GID to avoid conflicts)
RUN addgroup -g 1001 appuser && adduser -D -u 1001 -G appuser appuser
USER appuser

EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3000 || exit 1

CMD ["serve", "-s", "dist", "-l", "3000"]
