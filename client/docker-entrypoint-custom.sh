#!/bin/sh
set -e

# Получаем DNS resolver из /etc/resolv.conf
RESOLVER=$(grep -m1 "^nameserver" /etc/resolv.conf | awk '{print $2}')
if [ -z "$RESOLVER" ]; then
    RESOLVER="8.8.8.8"
fi
echo "Using DNS resolver: $RESOLVER"

# Запускаем стандартные nginx entrypoint скрипты (envsubst и т.д.)
# кроме финального запуска nginx
/docker-entrypoint.d/10-listen-on-ipv6-by-default.sh
. /docker-entrypoint.d/15-local-resolvers.envsh
/docker-entrypoint.d/20-envsubst-on-templates.sh
/docker-entrypoint.d/30-tune-worker-processes.sh

# Теперь подставляем resolver в уже сгенерированный конфиг
sed -i "s/RESOLVER_PLACEHOLDER/$RESOLVER/g" /etc/nginx/conf.d/default.conf

echo "Final nginx config resolver line:"
grep "resolver" /etc/nginx/conf.d/default.conf

# Запускаем nginx
exec nginx -g "daemon off;"
