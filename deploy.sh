#!/bin/bash
# Deploy Productivity Planner to a VPS (Vultr Dallas recommended)
# Usage: bash deploy.sh yourdomain.com
#
# Prerequisites:
#   1. Create a Vultr VPS: Cloud Compute, Dallas, Ubuntu 24.04, $5/mo
#   2. Point your domain's DNS A record to the VPS IP
#   3. SSH in: ssh root@YOUR_VPS_IP
#   4. Clone repo: git clone https://github.com/YOUR_USER/productivity.git && cd productivity
#   5. Run this script: bash deploy.sh yourdomain.com

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
echo "=== Generating VAPID keys ==="
pip3 install pywebpush 2>/dev/null
python3 -c "
from py_vapid import Vapid
v = Vapid()
v.generate_keys()
import base64
raw = v.private_key.private_bytes(
    encoding=__import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding']).Encoding.Raw,
    format=__import__('cryptography.hazmat.primitives.serialization', fromlist=['PrivateFormat']).PrivateFormat.Raw,
    encryption_algorithm=__import__('cryptography.hazmat.primitives.serialization', fromlist=['NoEncryption']).NoEncryption()
)
print('VAPID_PRIVATE_KEY=' + base64.urlsafe_b64encode(raw).decode())
pub = v.public_key.public_bytes(
    encoding=__import__('cryptography.hazmat.primitives.serialization', fromlist=['Encoding']).Encoding.Raw,
    format=__import__('cryptography.hazmat.primitives.serialization', fromlist=['PublicFormat']).PublicFormat.Raw,
)
print('VAPID_PUBLIC_KEY=' + base64.urlsafe_b64encode(pub).decode())
" 2>/dev/null || echo "(Could not auto-generate VAPID keys — generate manually)"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Create .env file:"
echo "     cp .env.example .env"
echo "     nano .env"
echo "     - Set PLANNER_PASSWORD to a strong password"
echo "     - Set JWT_SECRET to a random string (run: openssl rand -hex 32)"
echo "     - Set VAPID keys from above (or generate with: python3 -c 'from pywebpush import webpush')"
echo "     - Set VAPID_EMAIL to your email"
echo ""
echo "  2. Launch:"
echo "     docker compose up -d"
echo ""
echo "  3. Access at: https://$DOMAIN"
echo ""
echo "  4. Install on phone: Open in Safari > Share > Add to Home Screen"
