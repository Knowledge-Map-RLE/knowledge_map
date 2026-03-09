FROM node:18-alpine AS builder

WORKDIR /app

COPY package.json bun.lock* ./

RUN npm install -g bun

RUN bun install --frozen-lockfile

COPY . .

RUN bun run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# Шаблон конфига — подстановка API_HOST происходит при старте контейнера
COPY nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 80

# nginx:alpine официально поддерживает /etc/nginx/templates/ с envsubst
CMD ["nginx", "-g", "daemon off;"]