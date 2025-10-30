#!/bin/sh
set -eu

TEMPLATE=/etc/nginx/nginx.conf.template
NGINX_CONF=/etc/nginx/nginx.conf
DEFAULT_CONF=/etc/nginx/conf.d/default.conf

# Copy template to nginx.conf so it contains the log_format etc.
if [ -f "$TEMPLATE" ]; then
  cp "$TEMPLATE" "$NGINX_CONF"
fi

BLUE=${BLUE_SERVICE_HOST:-app_blue}
GREEN=${GREEN_SERVICE_HOST:-app_green}
APP_PORT=${APP_PORT:-3000}
ACTIVE_POOL=${ACTIVE_POOL:-blue}

if [ "$ACTIVE_POOL" = "green" ]; then
  PRIMARY_HOST=$GREEN
  BACKUP_HOST=$BLUE
else
  PRIMARY_HOST=$BLUE
  BACKUP_HOST=$GREEN
fi

cat > "$DEFAULT_CONF" <<EOF
upstream backend {
    server ${PRIMARY_HOST}:${APP_PORT};
    server ${BACKUP_HOST}:${APP_PORT} backup;
}

server {
    listen 8080;
    server_name localhost;

    # main location: proxy to backend (primary with automatic fallback to backup)
    location / {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;

        # Retry conditions to trigger fallback
        proxy_next_upstream error timeout invalid_header http_500 http_502 http_503 http_504;
        proxy_connect_timeout 2s;
        proxy_read_timeout 5s;

        # preserve upstream headers like X-Release-Id if backend sets it
        proxy_pass_header X-Release-Id;
    }
}
EOF

# ensure log directory exists
mkdir -p /var/log/nginx
chown -R nginx:nginx /var/log/nginx 2>/dev/null || true

exec nginx -g "daemon off;"
