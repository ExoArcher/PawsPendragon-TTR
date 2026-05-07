#!/usr/bin/env python3
"""Deploy bot code to Cybrancee via SFTP."""

import os
import sys
import paramiko
from pathlib import Path

# SFTP Credentials
SFTP_HOST = "cybrancee-bot-na-west-23.cybrancee.com"
SFTP_PORT = 2022
SFTP_USER = "ilkmjqd5.6265dfe8"
SFTP_PASS = "2#P5Ra#vv2.-$Kx"
REMOTE_DIR = "/home/container/PDMain"
LOCAL_DIR = "PDMain"

def deploy():
    """Deploy bot code via SFTP."""
    print(f"Deploying bot code to Cybrancee...")
    print(f"Host: {SFTP_HOST}:{SFTP_PORT}")
    print(f"User: {SFTP_USER}")
    print(f"Local: {LOCAL_DIR}/")
    print(f"Remote: {REMOTE_DIR}/")
    print()

    # Check local directory exists
    if not os.path.isdir(LOCAL_DIR):
        print(f"Error: {LOCAL_DIR}/ not found")
        sys.exit(1)

    try:
        # Connect via SFTP
        transport = paramiko.Transport((SFTP_HOST, SFTP_PORT))
        transport.connect(username=SFTP_USER, password=SFTP_PASS)
        sftp = paramiko.SFTPClient.from_transport(transport)

        print("Connected to SFTP server")
        print()

        # Upload files recursively
        uploaded = 0
        for root, dirs, files in os.walk(LOCAL_DIR):
            # Calculate remote path
            rel_path = os.path.relpath(root, LOCAL_DIR)
            if rel_path == ".":
                remote_path = REMOTE_DIR
            else:
                remote_path = f"{REMOTE_DIR}/{rel_path}".replace("\\", "/")

            # Ensure remote directory exists
            try:
                sftp.stat(remote_path)
            except IOError:
                print(f"  mkdir {remote_path}")
                sftp.mkdir(remote_path)

            # Upload files
            for file in files:
                local_file = os.path.join(root, file)
                remote_file = f"{remote_path}/{file}".replace("\\", "/")
                sftp.put(local_file, remote_file)
                uploaded += 1
                print(f"  put {local_file} -> {remote_file}")

        print()
        print(f"Uploaded {uploaded} file(s)")
        sftp.close()
        transport.close()
        print()
        print("Deployment complete!")

    except paramiko.AuthenticationException:
        print("Error: Authentication failed")
        sys.exit(1)
    except paramiko.SSHException as e:
        print(f"Error: SSH failed - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    deploy()
