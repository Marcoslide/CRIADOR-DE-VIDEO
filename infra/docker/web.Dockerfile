# Imagem do frontend (Fase 1: servidor de desenvolvimento Vite). Build de produção
# (assets estáticos + nginx) é uma otimização de infra para uma fase futura de
# hardening — fora de escopo da Fase 1 (Foundation).
FROM node:22-slim

WORKDIR /workspace

COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm install

COPY apps/web .

EXPOSE 5173
CMD ["npm", "run", "dev"]
