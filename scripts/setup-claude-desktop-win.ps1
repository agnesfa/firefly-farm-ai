# Firefly Corner Farm — Claude Desktop Setup for Windows
#
# Sets up the farmOS MCP server so Claude Desktop can manage farm data.
# Run from the repo root: .\scripts\setup-claude-desktop-win.ps1
#
# Prerequisites:
#   - Python 3.13 (download from python.org, check "Add to PATH")
#   - Claude Desktop installed

$ErrorActionPreference = "Stop"

$RepoDir = Split-Path -Parent $PSScriptRoot
$McpDir = Join-Path $RepoDir "mcp-server"

Write-Host "=== Firefly Corner Farm - Claude Desktop Setup (Windows) ===" -ForegroundColor Green
Write-Host ""

# -- Check Python 3.13 -------------------------------------------------

$Python = $null
foreach ($cmd in @("python3.13", "python3", "python")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "3\.13") {
            $Python = $cmd
            break
        }
    } catch { }
}

if (-not $Python) {
    Write-Host "ERROR: Python 3.13 is required." -ForegroundColor Red
    Write-Host "Download from https://www.python.org/downloads/"
    Write-Host "Make sure to check 'Add Python to PATH' during installation."
    exit 1
}
Write-Host "Found: $(& $Python --version)"

# -- Create venv --------------------------------------------------------

$VenvDir = Join-Path $McpDir "venv"
if (-not (Test-Path $VenvDir)) {
    Write-Host "Creating virtual environment..."
    & $Python -m venv $VenvDir
} else {
    Write-Host "Virtual environment already exists."
}

# -- Install dependencies -----------------------------------------------

$PipPath = Join-Path $VenvDir "Scripts\pip.exe"
$ReqPath = Join-Path $McpDir "requirements.txt"
Write-Host "Installing dependencies..."
& $PipPath install -q -r $ReqPath

# -- Verify --------------------------------------------------------------

$PythonPath = Join-Path $VenvDir "Scripts\python.exe"
& $PythonPath -c "import fastmcp; import requests; print('OK: All dependencies installed')"

# -- Generate config -----------------------------------------------------

$ServerPath = Join-Path $McpDir "server.py"
$ConfigDir = Join-Path $env:APPDATA "Claude"
$ConfigFile = Join-Path $ConfigDir "claude_desktop_config.json"

# Escape backslashes for JSON
$PythonPathJson = $PythonPath.Replace("\", "\\")
$ServerPathJson = $ServerPath.Replace("\", "\\")

Write-Host ""
Write-Host "=== Claude Desktop Configuration ===" -ForegroundColor Green
Write-Host "Config file: $ConfigFile"
Write-Host ""

if (-not (Test-Path $ConfigDir)) {
    New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
}

if (Test-Path $ConfigFile) {
    Write-Host "WARNING: $ConfigFile already exists." -ForegroundColor Yellow
    Write-Host "Add the farmos server config manually, or back up and replace."
    Write-Host ""
}

Write-Host "Copy this into your claude_desktop_config.json:"
Write-Host ""
Write-Host @"
{
  "mcpServers": {
    "farmos": {
      "command": "$PythonPathJson",
      "args": ["$ServerPathJson"],
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
"@

Write-Host ""
Write-Host "Replace YOUR_USERNAME and YOUR_PASSWORD with farmOS credentials."
Write-Host "Then restart Claude Desktop to connect."
Write-Host ""
Write-Host "=== Done ===" -ForegroundColor Green
