FROM node:22-alpine AS web-builder

WORKDIR /app
COPY web/package*.json ./
RUN npm ci

COPY web ./
RUN npm run build

FROM caddy:2.8-alpine
COPY --from=web-builder /app/dist /srv/web
