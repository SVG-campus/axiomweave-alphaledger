#!/usr/bin/env bash
set -euo pipefail

metadata() {
  curl --fail --silent --show-error \
    -H 'Metadata-Flavor: Google' \
    "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"
}

REPOSITORY_URL="$(metadata repo-url)"
REPOSITORY_REF="$(metadata repo-ref)"
PROJECT_ID="project-757198e6-df23-4e75-b08"
APP_ROOT="/opt/alphaledger"
VENV_ROOT="/opt/alphaledger-venv"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
  ca-certificates curl git jq nginx python3 python3-venv

groupadd --system alphaledger || true
useradd --system --gid alphaledger --home-dir /nonexistent --shell /usr/sbin/nologin alphaledger-demo || true
useradd --system --gid alphaledger --home-dir /nonexistent --shell /usr/sbin/nologin alphaledger-runner || true

if [[ -e "$APP_ROOT" ]]; then
  echo "Refusing to overwrite an existing application root" >&2
  exit 1
fi
git clone --filter=blob:none "$REPOSITORY_URL" "$APP_ROOT"
git -C "$APP_ROOT" checkout --detach "$REPOSITORY_REF"

python3 -m venv "$VENV_ROOT"
"$VENV_ROOT/bin/pip" install --disable-pip-version-check --no-cache-dir "$APP_ROOT"
"$VENV_ROOT/bin/python" "$APP_ROOT/scripts/verify.py"

ALPACA_VERSION="0.0.14"
ALPACA_ARCHIVE="cli_${ALPACA_VERSION}_linux_amd64.tar.gz"
ALPACA_SHA256="6c82ef31f94dd61aae1c90e40fc41fdfaf8111bd50e9a2780b9d8d304eb2ba66"
ALPACA_TMP="$(mktemp -d)"
trap 'rm -rf -- "$ALPACA_TMP"' EXIT
curl --fail --location --silent --show-error \
  "https://github.com/alpacahq/cli/releases/download/v${ALPACA_VERSION}/${ALPACA_ARCHIVE}" \
  --output "$ALPACA_TMP/$ALPACA_ARCHIVE"
echo "$ALPACA_SHA256  $ALPACA_TMP/$ALPACA_ARCHIVE" | sha256sum --check --status
tar -xzf "$ALPACA_TMP/$ALPACA_ARCHIVE" -C "$ALPACA_TMP"
install -m 0755 "$ALPACA_TMP/alpaca" /usr/local/bin/alpaca
/usr/local/bin/alpaca version

install -d -o root -g alphaledger -m 0750 /etc/alphaledger
install -d -o alphaledger-runner -g alphaledger -m 0750 "$APP_ROOT/var"
chmod -R go-w "$APP_ROOT"

cat >/usr/local/sbin/alphaledger-load-secrets <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
PROJECT_ID="project-757198e6-df23-4e75-b08"
TOKEN="$(curl --fail --silent --show-error -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token \
  | jq -r .access_token)"
read_secret() {
  local name="$1"
  curl --fail --silent --show-error \
    -H "Authorization: Bearer $TOKEN" \
    "https://secretmanager.googleapis.com/v1/projects/$PROJECT_ID/secrets/$name/versions/latest:access" \
    | jq -r .payload.data | base64 --decode
}
API_KEY="$(read_secret alphaledger-paper-api-key-20260828)"
API_SECRET="$(read_secret alphaledger-paper-api-secret-20260828)"
ACCOUNT_ID="$(read_secret alphaledger-paper-account-id-20260828)"
[[ "$API_KEY" =~ ^[A-Za-z0-9_-]{8,200}$ ]]
[[ "$API_SECRET" =~ ^[A-Za-z0-9_-]{8,200}$ ]]
[[ "$ACCOUNT_ID" =~ ^[A-Za-z0-9_-]{4,100}$ ]]
TEMP_FILE="$(mktemp /etc/alphaledger/runner.env.XXXXXX)"
trap 'rm -f -- "$TEMP_FILE"' EXIT
printf 'APCA_API_KEY_ID=%s\nAPCA_API_SECRET_KEY=%s\nALPHALEDGER_EXPECTED_ACCOUNT_ID=%s\n' \
  "$API_KEY" "$API_SECRET" "$ACCOUNT_ID" >"$TEMP_FILE"
chown root:alphaledger "$TEMP_FILE"
chmod 0640 "$TEMP_FILE"
mv -f "$TEMP_FILE" /etc/alphaledger/runner.env
trap - EXIT
SCRIPT
chmod 0750 /usr/local/sbin/alphaledger-load-secrets

cat >/usr/local/sbin/alphaledger-runner-start <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
MODE="observe"
if [[ -f /etc/alphaledger/paper-enabled ]]; then
  MODE="paper"
  export ALPHALEDGER_PAPER_ORDER_ACK='I_UNDERSTAND_THIS_SUBMITS_A_PAPER_ORDER'
fi
unset ALPACA_LIVE_TRADE
exec /opt/alphaledger-venv/bin/python /opt/alphaledger/scripts/competition_runner.py \
  --mode "$MODE" --writer-id alphaledger-gcp-primary --interval-seconds 60
SCRIPT
chmod 0755 /usr/local/sbin/alphaledger-runner-start

cat >/etc/systemd/system/alphaledger-demo.service <<'UNIT'
[Unit]
Description=AxiomWeave AlphaLedger public demo
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=alphaledger-demo
Group=alphaledger
Environment=HOME=/tmp
WorkingDirectory=/opt/alphaledger
ExecStart=/opt/alphaledger-venv/bin/streamlit run app.py --server.headless=true --server.address=127.0.0.1 --server.port=8501
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadOnlyPaths=/opt/alphaledger /opt/alphaledger-venv
UnsetEnvironment=APCA_API_KEY_ID APCA_API_SECRET_KEY ALPACA_API_KEY ALPACA_SECRET_KEY ALPACA_LIVE_TRADE

[Install]
WantedBy=multi-user.target
UNIT

cat >/etc/systemd/system/alphaledger-runner.service <<'UNIT'
[Unit]
Description=AxiomWeave AlphaLedger paper competition controller
After=network-online.target
Wants=network-online.target
ConditionPathExists=/etc/alphaledger/runner.env

[Service]
Type=simple
User=alphaledger-runner
Group=alphaledger
Environment=HOME=/tmp
WorkingDirectory=/opt/alphaledger
EnvironmentFile=/etc/alphaledger/runner.env
ExecStart=/usr/local/sbin/alphaledger-runner-start
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadOnlyPaths=/opt/alphaledger /opt/alphaledger-venv /etc/alphaledger
ReadWritePaths=/opt/alphaledger/var
UnsetEnvironment=ALPACA_LIVE_TRADE

[Install]
WantedBy=multi-user.target
UNIT

cat >/etc/nginx/sites-available/alphaledger <<'NGINX'
server {
    listen 80 default_server;
    server_name _;
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }
}
NGINX
rm -f /etc/nginx/sites-enabled/default
ln -s /etc/nginx/sites-available/alphaledger /etc/nginx/sites-enabled/alphaledger
nginx -t
systemctl daemon-reload
systemctl enable --now alphaledger-demo
systemctl enable nginx
systemctl restart nginx
systemctl disable alphaledger-runner.service || true
