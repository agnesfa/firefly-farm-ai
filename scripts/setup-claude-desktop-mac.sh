#!/bin/bash
# Firefly Corner Farm — Claude Desktop Setup for macOS
#
# Sets up the farmOS MCP server so Claude Desktop can manage farm data.
# Run from the repo root: ./scripts/setup-claude-desktop-mac.sh
#
# Prerequisites:
#   - Python 3.13 (brew install python@3.13)
#   - Claude Desktop installed

set -e

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MCP_DIR="$REPO_DIR/mcp-server"
CONFIG_DIR="$HOME/Library/Application Support/Claude"
CONFIG_FILE="$CONFIG_DIR/claude_desktop_config.json"

echo "=== Firefly Corner Farm — Claude Desktop Setup (macOS) ==="
echo ""

# ── Check Python 3.13 ────────────────────────────────────────

PYTHON=""
for candidate in python3.13 python3; do
    if command -v "$candidate" &>/dev/null; then
        version=$("$candidate" --version 2>&1)
        if echo "$version" | grep -q "3\.13"; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "ERROR: Python 3.13 is required."
    echo "Install via: brew install python@3.13"
    exit 1
fi
echo "Found $($PYTHON --version)"

# ── Create venv ───────────────────────────────────────────────

if [ ! -d "$MCP_DIR/venv" ]; then
    echo "Creating virtual environment..."
    "$PYTHON" -m venv "$MCP_DIR/venv"
else
    echo "Virtual environment already exists."
fi

# ── Install dependencies ──────────────────────────────────────

echo "Installing dependencies..."
"$MCP_DIR/venv/bin/pip" install -q -r "$MCP_DIR/requirements.txt"

# ── Verify ────────────────────────────────────────────────────

"$MCP_DIR/venv/bin/python" -c "import fastmcp; import requests; print('OK: All dependencies installed')"

# ── Generate config ───────────────────────────────────────────

PYTHON_PATH="$MCP_DIR/venv/bin/python"
SERVER_PATH="$MCP_DIR/server.py"

echo ""
echo "=== Claude Desktop Configuration ==="
echo ""
echo "Config file: $CONFIG_FILE"
echo ""

# Create config directory if needed
mkdir -p "$CONFIG_DIR"

if [ -f "$CONFIG_FILE" ]; then
    echo "WARNING: $CONFIG_FILE already exists."
    echo "Add the farmos server config manually, or back up and replace."
    echo ""
fi

echo "Copy this into your claude_desktop_config.json:"
echo ""
cat <<EOF
{
  "mcpServers": {
    "farmos": {
      "command": "$PYTHON_PATH",
      "args": ["$SERVER_PATH"],
      "env": {
        "FARMOS_URL": "https://margregen.farmos.net",
        "FARMOS_CLIENT_ID": "farm",
        "FARMOS_USERNAME": "YOUR_USERNAME",
        "FARMOS_PASSWORD": "YOUR_PASSWORD",
        "FARMOS_SCOPE": "farm_manager",
        "OBSERVE_ENDPOINT": "https://script.google.com/macros/s/AKfycbwxz3n9MSH45tQ1KX1_MacGAheIP_KcFMmlX_AWnYMI4-wwQ0ZNjYO5U8DJqHebcGPa/exec"
      }
    }
  }
}
EOF

echo ""
echo "Replace YOUR_USERNAME and YOUR_PASSWORD with farmOS credentials."
echo "Then restart Claude Desktop to connect."
echo ""
echo "=== Done ==="
