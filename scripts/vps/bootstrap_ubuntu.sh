#!/usr/bin/env bash
set -euo pipefail

# Ubuntu 24.04 bootstrap for WISO GoLabel backend
# Usage:
#   sudo bash bootstrap_ubuntu.sh

export DEBIAN_FRONTEND=noninteractive

apt-get update -y
apt-get upgrade -y

apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  nginx \
  certbot \
  python3-certbot-nginx \
  ufw \
  fail2ban \
  rsync \
  git \
  htop \
  jq \
  sqlite3

# Basic firewall policy
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
# Optional direct app port for temporary diagnostics
ufw allow 8080/tcp
ufw --force enable

# fail2ban sane defaults for ssh
systemctl enable fail2ban
systemctl restart fail2ban

# Create app user and directories
id -u wiso >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash wiso
install -d -o wiso -g wiso /opt/wiso-golabel
install -d -o wiso -g wiso /var/lib/wiso-golabel
install -d -o wiso -g wiso /var/backups/wiso-golabel

# Tighten SSH root password login (recommended after key setup)
if grep -qE '^#?PermitRootLogin' /etc/ssh/sshd_config; then
  sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
else
  echo 'PermitRootLogin prohibit-password' >> /etc/ssh/sshd_config
fi
if grep -qE '^#?PasswordAuthentication' /etc/ssh/sshd_config; then
  sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
fi
systemctl reload ssh || systemctl reload sshd || true

echo '[OK] Bootstrap finished.'
echo 'Next: run deploy_server.sh after uploading code.'