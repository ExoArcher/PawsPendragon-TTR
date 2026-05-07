#!/bin/bash
# Deploy bot code to Cybrancee via SFTP
# Usage: ./deploy.sh

set -e

SFTP_HOST="cybrancee-bot-na-west-23.cybrancee.com"
SFTP_PORT="2022"
SFTP_USER="ilkmjqd5.6265dfe8"
SFTP_PASS="2#P5Ra#vv2.-\$Kx"
REMOTE_DIR="/home/container/PDMain"
LOCAL_DIR="PDMain"

echo "🚀 Deploying bot code to Cybrancee..."
echo "Host: $SFTP_HOST:$SFTP_PORT"
echo "User: $SFTP_USER"
echo "Local: $LOCAL_DIR"
echo "Remote: $REMOTE_DIR"
echo ""

# Use lftp for SFTP with password
lftp -u "$SFTP_USER,$SFTP_PASS" -e "set sftp:auto-confirm yes; cd $REMOTE_DIR; mirror -R --delete $LOCAL_DIR .; quit" "sftp://$SFTP_HOST:$SFTP_PORT" 2>&1 | grep -E "(^|file|mirror)"

echo ""
echo "✅ Deployment complete"
