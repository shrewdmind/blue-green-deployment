#!/usr/bin/env sh
set -e

# --- Stage 3 Fixes: Ensure Log File Exists and has Correct Permissions ---

# 1. Create the log directory and file inside the shared volume
mkdir -p /var/log/nginx
touch /var/log/nginx/access.log
touch /var/log/nginx/error.log

# 2. Grant universal read access (r) so the 'alert_watcher' container (different user) can read it
# Nginx typically runs as UID 101, but the watcher runs as root, this ensures cross-container access.
chmod -R 777 /var/log/nginx || true

# --- Existing Stage 2/3 Logic ---

# Copy main template to the standard Nginx config file path
if [ -f /etc/nginx/nginx.conf.template ]; then
  cp /etc/nginx/nginx.conf.template /etc/nginx/nginx.conf
fi

# Default envs (sensible fallbacks)
: "${ACTIVE_POOL:=blue}"
: "${BLUE_SERVICE_HOST:=app_blue}"
: "${GREEN_SERVICE_HOST:=app_green}"
: "${APP_PORT:=3000}"

# Generate per-stage upstream + server conf (Keep your Stage 2 logic here)
cat > /etc/nginx/conf.d/default.conf <<EOF
upstream upstream_blue {
  server ${BLUE_SERVICE_HOST}:${APP_PORT};
}
upstream upstream_green {
  server ${GREEN_SERVICE_HOST}:${APP_PORT};
}

server {
  listen 8080;

  location / {
    # ... (Your proxy_pass logic remains unchanged) ...
    set \$target_upstream "upstream_${ACTIVE_POOL}";
    proxy_pass http://\$target_upstream;

    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;

    # Headers from app used for logging
    proxy_pass_request_headers on;
    proxy_set_header X-App-Pool \$http_x_app_pool;
    proxy_set_header X-Release-Id \$http_x_release_id;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
  }
}
EOF

# exec nginx
exec nginx -g 'daemon off;'