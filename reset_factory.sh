#!/usr/bin/env bash
# Factory reset — wipes all users and bookmarks from both databases.
# Must be run with sudo. Never copied into the Docker image (see .dockerignore).

set -euo pipefail

# ---------------------------------------------------------------------------
# Sudo guard
# ---------------------------------------------------------------------------
if [[ "${EUID}" -ne 0 ]]; then
  echo "[ERROR] This script must be run with sudo:" >&2
  echo "        sudo ./reset_factory.sh" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Locate docker compose
# ---------------------------------------------------------------------------
COMPOSE_CMD=""
if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
  COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
  COMPOSE_CMD="docker-compose"
else
  echo "[ERROR] docker compose not found." >&2
  exit 1
fi

# Resolve the directory that contains this script (works from any CWD)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VOLUME_NAME="bookmark_data"
CONTAINER_NAME="bookmark-manager"

# ---------------------------------------------------------------------------
# Warning banner
# ---------------------------------------------------------------------------
echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║           SANDBOX99 BOOKMARK — FACTORY RESET         ║"
echo "  ╠══════════════════════════════════════════════════════╣"
echo "  ║  This will permanently delete:                       ║"
echo "  ║    • All user accounts                               ║"
echo "  ║    • All bookmarks and category metadata             ║"
echo "  ║    • All session data                                ║"
echo "  ║                                                      ║"
echo "  ║  The application will be restarted automatically.    ║"
echo "  ║  THIS ACTION CANNOT BE UNDONE.                       ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo ""
read -rp "  Type RESET to confirm: " CONFIRM

if [[ "${CONFIRM}" != "RESET" ]]; then
  echo "[ABORT] Factory reset cancelled."
  exit 0
fi

echo ""
echo "[1/4] Stopping container..."
cd "${SCRIPT_DIR}"
${COMPOSE_CMD} down --timeout 10

echo "[2/4] Removing database files from volume '${VOLUME_NAME}'..."
docker run --rm \
  -v "${VOLUME_NAME}:/data" \
  alpine:latest \
  sh -c "rm -f /data/auth.db /data/bookmarks.db && echo 'Databases removed.'"

echo "[3/4] Restarting application..."
${COMPOSE_CMD} up -d

echo "[4/4] Waiting for container to become healthy..."
SECONDS_WAITED=0
until docker inspect --format='{{.State.Status}}' "${CONTAINER_NAME}" 2>/dev/null | grep -q "running"; do
  sleep 1
  SECONDS_WAITED=$((SECONDS_WAITED + 1))
  if [[ ${SECONDS_WAITED} -ge 30 ]]; then
    echo "[WARN] Container did not reach running state within 30 s — check logs:"
    echo "       docker logs ${CONTAINER_NAME}"
    exit 1
  fi
done

echo ""
echo "  Factory reset complete. Fresh databases will be"
echo "  initialised on first request to the application."
echo ""
