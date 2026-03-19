# Multi-stage Docker build for FarmOS MCP Server
# Optimized for Railway deployment
#
# Usage:
#   docker build -t farm-mcp-server .
#   docker run -p 3010:3010 -v /path/to/secrets:/app/secrets farm-mcp-server

# Stage 1: Dependencies and build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files for dependency installation
COPY package*.json ./
COPY apps/farm-server/package*.json ./apps/farm-server/
COPY plugins/farm-plugin/package*.json ./plugins/farm-plugin/

# Copy packed framework dependencies
COPY packed-deps/ ./packed-deps/

# Install all dependencies (including devDependencies for building)
RUN npm ci --include=dev

# Copy source code
COPY . .

# Build the project
RUN npm run build

# Stage 2: Production runtime
FROM node:20-alpine AS runtime

# Create non-root user for security
RUN addgroup -g 1001 -S nodejs && \
    adduser -S farmuser -u 1001

WORKDIR /app

# Copy package files and packed deps to establish workspace structure
COPY package*.json ./
COPY apps/farm-server/package*.json ./apps/farm-server/
COPY plugins/farm-plugin/package*.json ./plugins/farm-plugin/
COPY packed-deps/ ./packed-deps/

# Install production dependencies only
RUN npm ci --omit=dev && npm cache clean --force

# Copy built artifacts from builder stage
COPY --from=builder --chown=farmuser:nodejs /app/plugins/farm-plugin/dist ./plugins/farm-plugin/dist
COPY --from=builder --chown=farmuser:nodejs /app/apps/farm-server/dist ./apps/farm-server/dist

# Fix ownership
RUN chown -R farmuser:nodejs /app

# Switch to non-root user
USER farmuser

# Expose port (Railway will override this via PORT env var)
EXPOSE 3010

# Environment variables with Railway-compatible defaults
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3010
ENV CREDENTIALS_PATH=/app/secrets/credentials.json

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD node -e "const http = require('http'); const options = { host: '0.0.0.0', port: process.env.PORT || 3010, path: '/health/live', timeout: 5000 }; const req = http.request(options, (res) => { process.exit(res.statusCode === 200 ? 0 : 1); }); req.on('error', () => process.exit(1)); req.on('timeout', () => process.exit(1)); req.end();"

# Start the FarmOS MCP Server
CMD ["npm", "run", "--workspace=@farm/farm-server", "start"]
