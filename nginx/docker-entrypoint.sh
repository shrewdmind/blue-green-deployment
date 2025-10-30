#!/bin/sh
set -eu

# Simple entrypoint for Nginx that:
# - copies the provided nginx.conf.template to /etc/nginx/nginx.conf
# - writes a default server conf that proxies to app_blue / app_green based on ACTIVE_POOL env
# - starts nginx in foreground

TEMPLATE=/etc/nginx/nginx.conf.template
NGINX_CONF=/etc/nginx/nginx.conf
DEFAULT_CONF=/etc/nginx/conf.d/default.conf

# Copy template if present
if [ -f "$TEMPLATE" ]; then
  cp "$TEMPLATE" "$NGINX_CONF"
fi

# Resolve upstream hostnames from env or defaults
BLUE=${BLUE_SERVICE_HOST:-app_blue}
GREEN=${GREEN_SERVICE_HOST:-app_green}
APP_PORT=${APP_PORT:-3000}
ACTIVE_POOL=${ACTIVE_POOL:-blue}

cat > "$DEFAULT_CONF" <<EOF
upstream pool_blue {
    server ${BLUE}:${APP_PORT};
}
upstream pool_green {
    server ${GREEN}:${APP_PORT};
}

server {
    listen 8080;
    server_name localhost;

    # proxy settings
    location / {
        # Choose upstream based on active pool header -- by default we use ACTIVE_POOL
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;

        # Let backends set headers to identify pool & release:
        proxy_set_header X-App-Pool \$upstream_http_x_app_pool;
        proxy_set_header X-Release-Id \$upstream_http_x_release_id;

        # Health-based proxy pass: main and fallback configured; we will use simple proxy_pass with upstream balancer.
        proxy_next_upstream error timeout invalid_header http_500 http_502 http_503 http_504;
        
        # dynamic selection using ACTIVE_POOL environment variable (substituted at container start)
        proxy_pass http://pool_${ACTIVE_POOL};
        proxy_set_header X-Active-Pool ${ACTIVE_POOL};
    }
}
EOF

# Ensure log dir exists
mkdir -p /var/log/nginx
chown -R nginx:nginx /var/log/nginx || true

# Exec nginx
exec nginx -g "daemon off;"
