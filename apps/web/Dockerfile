# Frontend web image (build context = apps/web)
# NEXT_PUBLIC_* injects backend URLs at build time; when unset, next.config.js defaults (127.0.0.1:8081) apply.
FROM node:24-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24-slim AS builder
WORKDIR /app
# env.ts requires the three NEXT_PUBLIC_* vars in production (missing => unusable pages).
# Defaults match single-host deploy (web+api on one machine, API mapped to 8081); override with --build-arg for split deploys.
ARG NEXT_PUBLIC_API_BASE=http://localhost:8081
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8081
ARG NEXT_PUBLIC_STREAM_API_BASE=http://localhost:8081
ENV NEXT_TELEMETRY_DISABLED=1 \
    NEXT_PUBLIC_API_BASE=$NEXT_PUBLIC_API_BASE \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL \
    NEXT_PUBLIC_STREAM_API_BASE=$NEXT_PUBLIC_STREAM_API_BASE
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24-slim AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1
COPY --from=builder /app ./
EXPOSE 8080
CMD ["npm", "start", "--", "-p", "8080"]
