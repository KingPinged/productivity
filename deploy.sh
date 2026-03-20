#!/bin/bash
# Run on the VPS after first SSH login
# Usage: bash deploy.sh yourdomain.com

DOMAIN=$1
if [ -z "$DOMAIN" ]; then
    echo "Usage: bash deploy.sh yourdomain.com"
    exit 1
fi

echo "=== Installing Docker ==="
curl -fsSL https://get.docker.com | sh

echo "=== Installing Nginx + Certbot ==="
apt-get update && apt-get install -y nginx certbot python3-certbot-nginx

echo "=== Getting SSL Certificate ==="
certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN

echo "=== Configuring Nginx ==="
sed -i "s/DOMAIN/$DOMAIN/g" nginx/planner.conf
cp nginx/planner.conf /etc/nginx/sites-available/planner
ln -sf /etc/nginx/sites-available/planner /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo ""
echo "=== Setup Complete ==="
echo "1. Create .env file with: PLANNER_PASSWORD, JWT_SECRET, VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_EMAIL"
echo "2. Run: docker compose up -d"
echo "3. Access at: https://$DOMAIN"
