#!/bin/bash
# ============================================
# Dashboard Roblox - Termux Start Script
# Untuk Redfinger / Android Device
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================"
echo "  Dashboard Roblox - Starting..."
echo "============================================"
echo ""

# Check if running in Termux
if [ -z "$TERMUX_VERSION" ] && [ ! -d "/data/data/com.termux" ]; then
    echo "[ERROR] Script ini harus dijalankan di Termux!"
    exit 1
fi

# Start ADB server
echo "[*] Starting ADB server..."
adb start-server 2>/dev/null || true

# Check ADB devices
echo "[*] Checking ADB devices..."
adb devices 2>/dev/null || echo "[WARN] ADB devices check failed"

# Try to connect to local emulator
SERIAL="${ADB_SERIAL:-127.0.0.1:5555}"
echo "[*] Connecting to emulator at $SERIAL..."
adb connect "$SERIAL" 2>/dev/null || echo "[WARN] Could not connect to $SERIAL (connect manually if needed)"

# Start cloudflared tunnel if available
if command -v cloudflared &> /dev/null; then
    echo "[*] Starting Cloudflare Tunnel..."
    cloudflared tunnel --url http://localhost:5000 > /tmp/cloudflared.log 2>&1 &
    CF_PID=$!
    sleep 5
    TUNNEL_URL=$(grep -oP 'https://[a-zA-Z0-9-]+\.trycloudflare\.com' /tmp/cloudflared.log | head -1)
    if [ -n "$TUNNEL_URL" ]; then
        echo "[OK] Cloudflare Tunnel: $TUNNEL_URL"
        echo "[*] Set 'Dashboard URL' di Settings ke: $TUNNEL_URL"
    else
        echo "[WARN] Cloudflare Tunnel started but URL not found yet"
        echo "[*] Check /tmp/cloudflared.log for URL"
    fi
else
    echo "[INFO] cloudflared not found - using local access only"
    echo "[*] Install: pkg install cloudflared"
fi

echo ""
echo "============================================"
echo "  Dashboard Info"
echo "============================================"
echo ""
echo "Local:       http://localhost:5000"
echo "ADB Serial:  $SERIAL"
echo ""
echo "Tekan Ctrl+C untuk stop"
echo "============================================"
echo ""

# Run the dashboard
python app.py

# Cleanup on exit
if [ -n "$CF_PID" ]; then
    kill $CF_PID 2>/dev/null || true
fi
