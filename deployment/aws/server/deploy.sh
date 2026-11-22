#!/usr/bin/env bash
# Pull the latest image and (re)start FlowLytix. Run with: sudo /opt/flowlytix/deploy.sh
set -euo pipefail
cd /opt/flowlytix

env_value() { grep -E "^$1=" .env | tail -n 1 | cut -d= -f2- || true; }

IMAGE_URI="$(env_value IMAGE_URI)"
SITE_MODE="$(env_value SITE_MODE)"
SECRET="$(env_value FLOWTOOL_SECRET_KEY)"
SITE_MODE="${SITE_MODE:-ip}"

[[ -n "$IMAGE_URI" ]] || { echo "IMAGE_URI is empty in .env" >&2; exit 1; }
[[ ${#SECRET} -ge 32 ]] || { echo "FLOWTOOL_SECRET_KEY in .env must be at least 32 characters" >&2; exit 1; }
[[ "$SITE_MODE" == "ip" || "$SITE_MODE" == "sslip" ]] || { echo "SITE_MODE must be ip or sslip" >&2; exit 1; }

# Public IP from instance metadata (IMDSv2). Attach the Elastic IP before running this.
TOKEN="$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H 'X-aws-ec2-metadata-token-ttl-seconds: 60')"
PUBLIC_IP="$(curl -fsS -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4)"
[[ "$PUBLIC_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || { echo "No public IPv4 found. Attach the Elastic IP first." >&2; exit 1; }

if [[ "$SITE_MODE" == "ip" ]]; then
  SITE_ADDRESS="$PUBLIC_IP"
else
  SITE_ADDRESS="${PUBLIC_IP//./-}.sslip.io"
fi
export SITE_ADDRESS SITE_MODE

# Save it so later commands (docker compose logs, exec, ...) work without this script.
if grep -q '^SITE_ADDRESS=' .env; then
  sed -i "s|^SITE_ADDRESS=.*|SITE_ADDRESS=$SITE_ADDRESS|" .env
else
  echo "SITE_ADDRESS=$SITE_ADDRESS" >> .env
fi

docker compose pull
docker compose up -d --remove-orphans --wait --wait-timeout 180
docker image prune -f >/dev/null

echo
echo "FlowLytix is running at: https://$SITE_ADDRESS/"
echo "Admin panel:              https://$SITE_ADDRESS/admin"
echo "Certificate progress:     sudo docker compose -f /opt/flowlytix/docker-compose.yml logs caddy"
