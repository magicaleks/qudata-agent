#!/bin/bash

set -e

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}QuData Agent Installation Script${NC}"
echo -e "${GREEN}================================${NC}"
echo ""

# Проверка API ключа
if [ -z "$1" ]; then
    echo -e "${RED}Error: API key is required${NC}"
    echo -e "${YELLOW}Usage: curl -fsSL https://raw.githubusercontent.com/magicaleks/qudata-agent/main/install.sh | sudo bash -s YOUR_API_KEY${NC}"
    exit 1
fi

API_KEY="$1"
REPO_URL="https://github.com/magicaleks/qudata-agent.git"
INSTALL_DIR="/opt/qudata-agent"

echo -e "${BLUE}Starting installation...${NC}"
echo ""

echo -e "${YELLOW}[1/10] Updating system packages...${NC}"
apt-get update -qq

echo -e "${YELLOW}[2/10] Installing system dependencies...${NC}"
apt-get install -y git curl wget software-properties-common \
    lsb-release ca-certificates apt-transport-https \
    ethtool dmidecode lshw pciutils > /dev/null 2>&1

echo -e "${YELLOW}[3/10] Checking Python 3.10+...${NC}"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2 || echo "0.0")
if [ "$(printf '%s\n' "3.10" "$PYTHON_VERSION" | sort -V | head -n1)" != "3.10" ]; then
    echo "Python 3.10+ not found, installing..."
    add-apt-repository -y ppa:deadsnakes/ppa > /dev/null 2>&1
    apt-get update -qq
    apt-get install -y python3.10 python3.10-venv python3.10-dev python3-pip > /dev/null 2>&1
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 > /dev/null 2>&1
fi
echo -e "${GREEN}✓ Python version: $(python3 --version)${NC}"

echo -e "${YELLOW}[4/10] Checking Docker...${NC}"
if ! command -v docker &> /dev/null; then
    echo "Docker not found, installing..."
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sh /tmp/get-docker.sh > /dev/null 2>&1
    usermod -aG docker root
    echo -e "${GREEN}✓ Docker installed${NC}"
else
    echo -e "${GREEN}✓ Docker already installed${NC}"
fi

echo -e "${YELLOW}[5/10] Checking for NVIDIA GPU...${NC}"
if lspci | grep -i nvidia > /dev/null 2>&1; then
    echo "NVIDIA GPU detected"
    
    if ! command -v nvidia-smi &> /dev/null; then
        echo "Installing NVIDIA drivers..."
        apt-get install -y linux-headers-$(uname -r) > /dev/null 2>&1
        apt-get install -y nvidia-driver-535 > /dev/null 2>&1
        echo -e "${YELLOW}⚠ NVIDIA driver installed. System reboot required!${NC}"
        echo -e "${YELLOW}After reboot, run this command again.${NC}"
        echo ""
        echo "Do you want to reboot now? (y/n)"
        read -r answer
        if [ "$answer" = "y" ]; then
            reboot
        fi
        exit 0
    else
        echo -e "${GREEN}✓ NVIDIA drivers already installed${NC}"
    fi
    
    echo -e "${YELLOW}[6/10] Installing NVIDIA Container Toolkit...${NC}"
    if ! dpkg -l | grep nvidia-container-toolkit > /dev/null 2>&1; then
        distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
            gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg 2>/dev/null
        curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
        apt-get update -qq
        apt-get install -y nvidia-container-toolkit > /dev/null 2>&1
        nvidia-ctk runtime configure --runtime=docker > /dev/null 2>&1
        systemctl restart docker
        echo -e "${GREEN}✓ NVIDIA Container Toolkit installed${NC}"
    else
        echo -e "${GREEN}✓ NVIDIA Container Toolkit already installed${NC}"
    fi
else
    echo -e "${YELLOW}⚠ No NVIDIA GPU detected, skipping GPU setup${NC}"
fi

echo -e "${YELLOW}[7/10] Cloning repository...${NC}"
if [ -d "$INSTALL_DIR" ]; then
    echo "Directory $INSTALL_DIR already exists, updating..."
    cd "$INSTALL_DIR"
    git fetch origin > /dev/null 2>&1
    git reset --hard origin/main > /dev/null 2>&1
    git pull > /dev/null 2>&1
else
    git clone "$REPO_URL" "$INSTALL_DIR" > /dev/null 2>&1
fi
echo -e "${GREEN}✓ Repository cloned/updated at $INSTALL_DIR${NC}"

echo -e "${YELLOW}[8/10] Installing Python dependencies...${NC}"
cd "$INSTALL_DIR"
pip3 install --upgrade pip > /dev/null 2>&1
pip3 install -r requirements.txt > /dev/null 2>&1
echo -e "${GREEN}✓ Python dependencies installed${NC}"

echo -e "${YELLOW}[9/10] Creating systemd service...${NC}"
cat > /etc/systemd/system/qudata-agent.service <<EOF
[Unit]
Description=QuData Agent
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/main.py $API_KEY
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable qudata-agent > /dev/null 2>&1
echo -e "${GREEN}✓ Systemd service created and enabled${NC}"

echo -e "${YELLOW}[10/10] Starting QuData Agent...${NC}"
systemctl restart qudata-agent
sleep 3

if systemctl is-active --quiet qudata-agent; then
    echo ""
    echo -e "${GREEN}================================${NC}"
    echo -e "${GREEN}✓ Installation completed successfully!${NC}"
    echo -e "${GREEN}================================${NC}"
    echo ""
    echo -e "${BLUE}QuData Agent is running as systemd service${NC}"
    echo ""
    echo -e "${YELLOW}Useful commands:${NC}"
    echo "  View logs:      sudo journalctl -u qudata-agent -f"
    echo "  View status:    sudo systemctl status qudata-agent"
    echo "  Stop agent:     sudo systemctl stop qudata-agent"
    echo "  Start agent:    sudo systemctl start qudata-agent"
    echo "  Restart agent:  sudo systemctl restart qudata-agent"
    echo ""
    echo -e "  Log file:       ${BLUE}$INSTALL_DIR/logs.txt${NC}"
    echo ""
    echo -e "${GREEN}Agent is ready to accept tasks!${NC}"
    echo ""
else
    echo ""
    echo -e "${RED}✗ Failed to start QuData Agent${NC}"
    echo ""
    echo "Check logs with: sudo journalctl -u qudata-agent -n 50"
    echo "Or check:        cat $INSTALL_DIR/logs.txt"
    exit 1
fi
