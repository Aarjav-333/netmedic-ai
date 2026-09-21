# ---- build stage ----
FROM node:20-alpine AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# Dependencies first so this layer is reused across source-only changes.
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# No backend URLs are baked in: the browser resolves them at runtime via /api/config
# (NETMEDIC_BACKEND_PORT / NETMEDIC_API_BASE_URL / NETMEDIC_WS_URL on the *running* container).
RUN npm run build

# ---- runtime stage ----
FROM node:20-alpine AS runtime
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
