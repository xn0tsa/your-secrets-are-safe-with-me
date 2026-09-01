#!/usr/bin/env bash
# Rogue AP setup to MITM the Eiliko
# macOS prerequisite: brew install dnsmasq
#
# STEPS:
# 1. Create a WiFi hotspot from macOS (Sharing > Internet)
# 2. Run this script → configures dnsmasq to spoof ai.energizelab.com.cn
# 3. Run fake_ai_server.py on port 8000
# 4. Reconnect the Eiliko to our hotspot via the app

set -e

OUR_IP=$(ipconfig getifaddr en0 || ifconfig bridge100 | grep "inet " | awk '{print $2}')
AI_DOMAIN="ai.energizelab.com.cn"
ADMIN_DOMAIN="45.32.81.33"

echo "=== EILIKO ROGUE AP SETUP ==="
echo "Notre IP sur le hotspot: $OUR_IP"
echo "Domaine à spoofer: $AI_DOMAIN → $OUR_IP"

# Vérifier dnsmasq
if ! command -v dnsmasq &>/dev/null; then
    echo "dnsmasq pas installé. Installer: brew install dnsmasq"
    exit 1
fi

# Config dnsmasq
DNSMASQ_CONF="/tmp/eiliko_dnsmasq.conf"
cat > "$DNSMASQ_CONF" << EOF
# Écouter sur l'interface hotspot
interface=bridge100
bind-interfaces

# Spoofing: pointer ai.energizelab.com.cn vers notre fake server
address=/$AI_DOMAIN/$OUR_IP

# Forwarder le reste vers DNS réel
server=8.8.8.8
server=8.8.4.4

# DHCP pour le réseau hotspot
dhcp-range=192.168.2.100,192.168.2.200,24h
dhcp-option=3,$OUR_IP    # Gateway
dhcp-option=6,$OUR_IP    # DNS → notre machine
EOF

echo "Config dnsmasq créée: $DNSMASQ_CONF"
cat "$DNSMASQ_CONF"

echo ""
echo "=== LANCEMENT dnsmasq ==="
# Arrêter dnsmasq existant si lancé
sudo killall dnsmasq 2>/dev/null || true
sudo dnsmasq --conf-file="$DNSMASQ_CONF" --log-queries --log-facility=/tmp/eiliko_dns.log
echo "dnsmasq lancé. Logs: /tmp/eiliko_dns.log"

echo ""
echo "=== INSTRUCTIONS ==="
echo "1. Activer le partage Internet macOS:"
echo "   Préférences Système → Partage → Partage de connexion"
echo "   Partager depuis: Wi-Fi (ou Ethernet)"
echo "   Vers: Wi-Fi (créer hotspot)"
echo ""
echo "2. Dans l'app Eiliko:"
echo "   Paramètres → WiFi → Connecter à notre hotspot"
echo ""
echo "3. Lancer le fake server:"
echo "   pip3 install fastapi uvicorn httpx anthropic"
echo "   ANTHROPIC_API_KEY=xxx python3 fake_ai_server.py"
echo "   # ou sans API key (mode démo):"
echo "   python3 fake_ai_server.py"
echo ""
echo "4. Vérifier le DNS spoof:"
echo "   nslookup $AI_DOMAIN"
echo "   → doit retourner $OUR_IP"
echo ""
echo "=== ALTERNATIVE: /etc/hosts sur le routeur ==="
echo "Si tu as accès au routeur (admin):"
echo "  Ajouter: $OUR_IP $AI_DOMAIN"
echo "  → Tous les devices du réseau seront redirigés"
