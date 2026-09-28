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
DYNAMODB_ZIP_URL="https://s3.us-west-2.amazonaws.com/dynamodb-local/v2.x/dynamodb_local_latest.zip"

yum install -y java-17-amazon-corretto-headless python3.12 git unzip

git clone "$REPO_URL" "$APP_DIR"
cd "$APP_DIR"

# Use python3.12 instead of python3 to ensure we use the correct version of Python
python3.12 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -e .
cp config/example.env .env

mkdir db
curl -fsSL -o /tmp/dynamodb_local.zip "$DYNAMODB_ZIP_URL"
unzip -o /tmp/dynamodb_local.zip -d db
rm -f /tmp/dynamodb_local.zip

# This script runs as root, but the app runs as ec2-user. Change ownership
# to ec2-user for all files created in the previous steps.
chown -R ec2-user:ec2-user "$APP_DIR"

cp deploy/dynamodb-local.service /etc/systemd/system/
cp deploy/voting.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now dynamodb-local.service

.venv/bin/python scripts/wait_for_dynamodb.py
.venv/bin/python scripts/create_table.py

systemctl enable --now tee-time.service