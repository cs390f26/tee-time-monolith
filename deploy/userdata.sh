#!/bin/bash
# EC2 user-data script to install the necessary packages, application code,
# configuration, database, and services.
#
# When you launch an instance, paste this file into the User data field.
# Cloud-init runs it once as root on first boot.
#
# All output is saved to /var/log/cloud-init-output.log.

# Exit on error, undefined variable, or failure in a pipeline.
set -euo pipefail

##############################################################################
##############################################################################
# CHANGE REPO_URL BELOW: REPLACE YOUR_GITHUB_USERNAME WITH YOUR GITHUB
# USERNAME. DO NOT CHANGE THE REPOSITORY NAME (tee-time-monolith).
##############################################################################
##############################################################################
REPO_URL="https://github.com/YOUR_GITHUB_USERNAME/tee-time-monolith.git"

APP_DIR=/home/ec2-user/tee-time-monolith

yum install -y python3.12 git sqlite

git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

# Use python3.12 instead of python3 to ensure we use the correct version of Python
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

cat > "$APP_DIR/.env" <<'EOF'
DATABASE_PATH=club.sqlite
EOF

# This script runs as root, but the app runs as ec2-user. Change ownership
# to ec2-user for all files created in the previous steps, then create the
# SQLite file as that user.
chown -R ec2-user:ec2-user "$APP_DIR"

sudo -u ec2-user sqlite3 "$APP_DIR/club.sqlite" < "$APP_DIR/scripts/schema.sql"
sudo -u ec2-user sqlite3 "$APP_DIR/club.sqlite" < "$APP_DIR/scripts/seed-data.sql"

cp deploy/tee-time.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tee-time.service
