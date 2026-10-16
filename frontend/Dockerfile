FROM node:24-alpine AS build
WORKDIR /app
# Pre-staging S6: exact dependency tree of the certified lockfile (reproducible build).
COPY package.json package-lock.json tsconfig.json ./
RUN npm ci
COPY . .
RUN npm run build
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
