#!/usr/bin/env sh
set -e

# Simple entrypoint to generate default upstream/server conf and then run nginx
# Uses environment variables:
# - ACTIVE_POOL (blue|green)
# - BLUE_SERVICE_HOST
# - GREEN_SERVICE_HOST
# - APP_PORT

# Copy main template if provided (so log_format is present)
if [ -f /etc/nginx/nginx.conf.template ]; then
  cp /etc/nginx/nginx.conf.template /etc/nginx/nginx.conf
fi

# Default envs (sensible fallbacks)
: "${ACTIVE_POOL:=blue}"
: "${BLUE_SERVICE_HOST:=app_blue}"
: "${GREEN_SERVICE_HOST:=app_green}"
: "${APP_PORT:=3000}"

# Generate per-stage upstream + server conf
cat > /etc/nginx/conf.d/default.conf <<EOF
upstream upstream_blue {
    server ${BLUE_SERVICE_HOST}:${APP_PORT};
}
upstream upstream_green {
    server ${GREEN_SERVICE_HOST}:${APP_PORT};
}

server {
    listen 8080;

    # proxy settings
    location / {
        # pick upstream based on ACTIVE_POOL env
        # we use the resolver trick: set $upstream dynamically via map-like if
        # simple approach: use proxy_pass with variable evaluated at runtime
        set \$target_upstream "upstream_${ACTIVE_POOL}";
        proxy_pass http://\$target_upstream;

        # preserve app headers that hold pool/release info
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;

        # set to receive upstream headers through proxy (app must set them)
        proxy_pass_request_headers on;

        # ensure we get upstream headers exposed to logs
        # allow upstream to set X-App-Pool and X-Release-Id headers
        proxy_set_header X-App-Pool \$http_x_app_pool;
        proxy_set_header X-Release-Id \$http_x_release_id;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }

    # health endpoint (optional)
    location /__health {
        return 200 "ok";
    }
}
EOF

# Ensure log ownership to avoid permission problem with mounted volume (best-effort)
mkdir -p /var/log/nginx
touch /var/log/nginx/access.log /var/log/nginx/error.log || true
chown -R nginx:nginx /var/log/nginx || true

# exec nginx
exec nginx -g 'daemon off;'
