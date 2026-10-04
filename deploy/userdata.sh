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
REPO_URL="https://github.com/cs390f26/tee-time-monolith.git"

APP_DIR=/home/ec2-user/tee-time-monolith

yum install -y python3.12 git mariadb105-server

systemctl enable --now mariadb

git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

# Use python3.12 instead of python3 to ensure we use the correct version of Python
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .

cat > "$APP_DIR/.env" <<'EOF'
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=tee_time
MYSQL_PASSWORD=tee_time
MYSQL_DATABASE=tee_time
EOF

# This script runs as root, but the app runs as ec2-user. Change ownership
# to ec2-user for all files created in the previous steps, then create the
# database as that user.
chown -R ec2-user:ec2-user "$APP_DIR"

mysql <<'EOF'
CREATE DATABASE IF NOT EXISTS tee_time;
CREATE USER IF NOT EXISTS 'tee_time'@'localhost' IDENTIFIED BY 'tee_time';
CREATE USER IF NOT EXISTS 'tee_time'@'127.0.0.1' IDENTIFIED BY 'tee_time';
GRANT ALL PRIVILEGES ON tee_time.* TO 'tee_time'@'localhost';
GRANT ALL PRIVILEGES ON tee_time.* TO 'tee_time'@'127.0.0.1';
FLUSH PRIVILEGES;
EOF

mysql -u tee_time -ptee_time tee_time < "$APP_DIR/scripts/schema.sql"
mysql -u tee_time -ptee_time tee_time < "$APP_DIR/scripts/seed-data.sql"

cp deploy/tee-time.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now tee-time.service
