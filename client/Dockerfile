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

# Кастомный entrypoint: подставляет DNS resolver из /etc/resolv.conf
COPY docker-entrypoint-custom.sh /docker-entrypoint-custom.sh
RUN chmod +x /docker-entrypoint-custom.sh

EXPOSE 80

ENTRYPOINT ["/docker-entrypoint-custom.sh"]
CMD ["/docker-entrypoint.sh", "nginx", "-g", "daemon off;"]