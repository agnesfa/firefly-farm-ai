# Multi-stage Docker build for FarmOS MCP Server
# Optimized for Railway deployment.
#
# BUILD CONTEXT: repo root (one level above this file), so we can COPY the
# canonical knowledge/ directory directly without duplicating it inside
# mcp-server-ts/. All Dockerfile paths are therefore rooted at the repo root.
#
# Railway settings required to match:
#   Root Directory  = /              (NOT /mcp-server-ts)
#   Dockerfile Path = mcp-server-ts/Dockerfile
#
# Local build:
#   docker build -f mcp-server-ts/Dockerfile -t farm-mcp-server .
#   docker run -p 3010:3010 -v /path/to/secrets:/app/secrets farm-mcp-server

# Stage 1: Dependencies and build
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files for dependency installation
COPY mcp-server-ts/package*.json ./
COPY mcp-server-ts/apps/farm-server/package*.json ./apps/farm-server/
COPY mcp-server-ts/plugins/farm-plugin/package*.json ./plugins/farm-plugin/

# Copy packed framework dependencies
COPY mcp-server-ts/packed-deps/ ./packed-deps/

# Install all dependencies (including devDependencies for building)
RUN npm ci --include=dev

# Copy the TypeScript workspace source (tsconfig, apps/, plugins/)
COPY mcp-server-ts/tsconfig.json ./
COPY mcp-server-ts/apps/ ./apps/
COPY mcp-server-ts/plugins/ ./plugins/

# Build the project
RUN npm run build

# Stage 2: Production runtime
FROM node:20-alpine AS runtime

# Create non-root user for security
RUN addgroup -g 1001 -S nodejs && \
    adduser -S farmuser -u 1001

WORKDIR /app

# Copy package files and packed deps to establish workspace structure
COPY mcp-server-ts/package*.json ./
COPY mcp-server-ts/apps/farm-server/package*.json ./apps/farm-server/
COPY mcp-server-ts/plugins/farm-plugin/package*.json ./plugins/farm-plugin/
COPY mcp-server-ts/packed-deps/ ./packed-deps/

# Install production dependencies only
RUN npm ci --omit=dev && npm cache clean --force

# Copy built artifacts from builder stage
COPY --from=builder --chown=farmuser:nodejs /app/plugins/farm-plugin/dist ./plugins/farm-plugin/dist
COPY --from=builder --chown=farmuser:nodejs /app/apps/farm-server/dist ./apps/farm-server/dist

# Copy CANONICAL knowledge base from repo root (farm_growth.yaml is read at
# runtime by the system_health tool). Previously this lived at
# mcp-server-ts/knowledge/ which drifted from the root copy — resolved by
# pointing the build context at the repo root.
COPY --chown=farmuser:nodejs knowledge/ ./knowledge/

# Copy entrypoint script
COPY --chown=farmuser:nodejs mcp-server-ts/docker-entrypoint.sh ./

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
