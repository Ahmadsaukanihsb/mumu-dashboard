#!/bin/bash
# ============================================
# Dashboard Roblox - Termux Setup (One-liner)
#
# Cara pakai (paste di Termux):
#   curl -sL https://raw.githubusercontent.com/USERNAME/REPO/main/setup_termux.sh | bash
#
# Atau manual:
#   pkg install curl
#   curl -sL https://raw.githubusercontent.com/USERNAME/REPO/main/setup_termux.sh | bash
# ============================================

set -e

echo "============================================"
echo "  Dashboard Roblox - Termux Setup"
echo "============================================"
echo ""

# Check if running in Termux
if [ -z "$TERMUX_VERSION" ] && [ ! -d "/data/data/com.termux" ]; then
    echo "[ERROR] Script ini harus dijalankan di Termux!"
    echo "Install Termux dari F-Droid: https://f-droid.org/en/packages/com.termux/"
    exit 1
fi

# GitHub repo URL (UPDATE INI setelah push ke GitHub!)
REPO_URL="${REPO_URL:-https://github.com/USERNAME/Dashboard-Roblox}"
BRANCH="${BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/dashboard-roblox}"

echo "[1/7] Updating packages..."
pkg update -y 2>/dev/null || apt update -y

echo "[2/7] Installing system packages..."
pkg install -y python adb git curl cloudflared 2>/dev/null || apt install -y python adb git curl cloudflared

echo "[3/7] Installing Python packages..."
pip install --upgrade pip 2>/dev/null || true
pip install flask flask-cors werkzeug

echo "[4/7] Downloading project..."
if [ -d "$INSTALL_DIR" ]; then
    echo "[*] Project already exists at $INSTALL_DIR, pulling latest..."
    cd "$INSTALL_DIR"
    git pull 2>/dev/null || true
else
    echo "[*] Cloning to $INSTALL_DIR..."
    git clone -b "$BRANCH" "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

echo "[5/7] Setting up storage..."
termux-setup-storage 2>/dev/null || echo "[WARN] termux-setup-storage failed (non-critical)"

echo "[6/7] Testing ADB..."
if command -v adb &> /dev/null; then
    adb version
    echo "[OK] ADB found"
else
    echo "[WARN] ADB not found in PATH"
    echo "Try: pkg install android-tools"
fi

echo "[7/7] Making scripts executable..."
chmod +x run_termux.sh 2>/dev/null || true
chmod +x setup_termux.sh 2>/dev/null || true

echo ""
echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo ""
echo "Langkah selanjutnya:"
echo "  1. Buka Roblox floating apps di device"
echo "  2. Buka Termux, jalankan:"
echo "     cd $INSTALL_DIR && bash run_termux.sh"
echo "  3. Copy Cloudflare Tunnel URL dari output"
echo "  4. Buka URL tersebut di browser PC"
echo "  5. Di Settings → Integrations → Dashboard URL:"
echo "     isi dengan Cloudflare Tunnel URL"
echo ""
echo "ADB Serial default: 127.0.0.1:5555"
echo ""
