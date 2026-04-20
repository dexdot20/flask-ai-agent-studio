#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="flask-rag-vision-chatbot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
APP_USER="${SUDO_USER:-${USER:-}}"
APP_GROUP="${APP_USER}"
WORKING_DIR="${ROOT_DIR}"
ENV_FILE="${WORKING_DIR}/.env"
APP_ENTRY="app:app"
VENV_DIR=""
PYTHON_BIN=""
GUNICORN_BIN=""

detect_virtualenv() {
  local candidate

  for candidate in "${WORKING_DIR}/.venv" "${WORKING_DIR}/venv"; do
    if [[ -x "${candidate}/bin/python" ]]; then
      VENV_DIR="${candidate}"
      PYTHON_BIN="${candidate}/bin/python"
      GUNICORN_BIN="${candidate}/bin/gunicorn"
      return 0
    fi
  done

  return 1
}

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This script only runs on Linux." >&2
  exit 1
fi

if [[ "$EUID" -ne 0 ]]; then
  echo "This script must be run as root or with sudo." >&2
  exit 1
fi

if [[ ! -d "${WORKING_DIR}" ]]; then
  echo "Project directory not found: ${WORKING_DIR}" >&2
  exit 1
fi

if ! detect_virtualenv; then
  echo "Virtual environment not found in ${WORKING_DIR}/.venv or ${WORKING_DIR}/venv." >&2
  echo "Install dependencies and create a virtual environment first." >&2
  exit 1
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  cat >&2 <<EOF
Warning: ${ENV_FILE} not found.
The service will still be created, but the app may be missing required environment variables at startup.
EOF
fi

if [[ -z "${APP_USER}" ]]; then
  echo "Could not resolve the user account." >&2
  exit 1
fi

if [[ ! -x "${GUNICORN_BIN}" ]]; then
  echo "gunicorn was not found in ${VENV_DIR}. Make sure it is installed." >&2
  exit 1
fi

if systemctl list-unit-files | grep -q "^${SERVICE_NAME}\.service"; then
  systemctl disable --now "${SERVICE_NAME}.service" >/dev/null 2>&1 || true
fi

rm -f "${SERVICE_FILE}"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=Flask RAG Vision Chatbot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${WORKING_DIR}
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-${ENV_FILE}
ExecStart=${GUNICORN_BIN} --bind 0.0.0.0:5000 --workers 1 --timeout 120 ${APP_ENTRY}
Restart=always
RestartSec=5
KillSignal=SIGINT
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "${SERVICE_FILE}"

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"
systemctl restart "${SERVICE_NAME}.service"

systemctl --no-pager --full status "${SERVICE_NAME}.service" || true

echo "Service installed: ${SERVICE_NAME}.service"
echo "You can run this again for a clean reinstall; the existing unit is removed and recreated first."
