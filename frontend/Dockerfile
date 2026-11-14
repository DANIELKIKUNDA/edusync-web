FROM node:24-alpine AS build
WORKDIR /app
# Pre-staging S6: exact dependency tree of the certified lockfile (reproducible build).
COPY package.json package-lock.json tsconfig.json ./
RUN npm ci
COPY . .
# Build identity shown by the update notice (commit SHA passed by the CI).
ARG EDUSYNC_BUILD_ID=
ENV EDUSYNC_BUILD_ID=$EDUSYNC_BUILD_ID
RUN npm run build
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Production Coolify seulement (docker-compose.coolify.yml) : même configuration + HSTS, schéma HTTPS de Traefik, flux live.
COPY nginx.production.conf /etc/nginx/edusync/production.conf
