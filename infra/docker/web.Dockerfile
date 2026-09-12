# Imagem do frontend — multi-stage.
#
#   target "dev"        servidor de desenvolvimento do Vite (docker-compose.override.yml,
#                        carregado automaticamente por `docker compose up`).
#   target "production"  build estático servido por nginx (docker-compose.prod.yml).
#
# Build a partir da raiz do monorepo:
#   docker build -f infra/docker/web.Dockerfile --target production -t dhf-web .

FROM node:22-slim AS deps
WORKDIR /workspace
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM deps AS dev
WORKDIR /workspace
COPY apps/web .
EXPOSE 5173
CMD ["npm", "run", "dev"]

FROM deps AS build
WORKDIR /workspace
COPY apps/web .
# VITE_API_URL é embutida no bundle estático no momento do build (padrão do Vite — não é
# lida em runtime pelo container). Precisa ser conhecida antes de buildar a imagem.
ARG VITE_API_URL
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM nginx:1.27-alpine AS production
COPY --from=build /workspace/dist /usr/share/nginx/html
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
