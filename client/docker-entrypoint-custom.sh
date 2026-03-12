#!/bin/sh
# Получаем DNS resolver из /etc/resolv.conf
RESOLVER=$(grep -m1 "^nameserver" /etc/resolv.conf | awk '{print $2}')
if [ -z "$RESOLVER" ]; then
    RESOLVER="8.8.8.8"
fi
echo "Using DNS resolver: $RESOLVER"

# Подставляем resolver в nginx.conf
sed -i "s/RESOLVER_PLACEHOLDER/$RESOLVER/g" /etc/nginx/conf.d/default.conf

exec "$@"
