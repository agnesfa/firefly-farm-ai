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

# Copy knowledge base (farm_growth.yaml needed by system_health tool)
COPY --chown=farmuser:nodejs knowledge/ ./knowledge/

# Copy entrypoint script
COPY --chown=farmuser:nodejs docker-entrypoint.sh ./

# Fix ownership and make entrypoint executable
RUN chown -R farmuser:nodejs /app && chmod +x /app/docker-entrypoint.sh

# Switch to non-root user
USER farmuser

# Expose port (Railway will override this via PORT env var)
EXPOSE 3010

# Environment variables with Railway-compatible defaults
ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3010
ENV CREDENTIALS_PATH=/app/secrets/credentials.json

# Railway handles healthchecks natively via /health path — no Docker HEALTHCHECK needed

# Entrypoint writes credentials from env var, then runs CMD
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["npm", "run", "--workspace=@farm/farm-server", "start"]
