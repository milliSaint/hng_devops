FROM node:20-bookworm-slim AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install --only=production

FROM node:20-bookworm-slim
RUN apt-get update && apt-get upgrade -y && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=builder /app/node_modules ./node_modules
COPY . .
RUN useradd -m appuser && chown -R appuser /app
USER appuser
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000', r => process.exit(r.statusCode === 200 ? 0 : 1))"
CMD ["node", "app.js"]
