"""Bounded SSH preflight emitting categories, never private addresses or keys."""

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path


def preflight(host: str, user: str, credentials: Path, *, use_ssm: bool = False) -> int:
    if not re.fullmatch(r"[A-Za-z0-9.-]+", host) or not re.fullmatch(r"[A-Za-z0-9_-]+", user):
        print("SSH preflight: missing or invalid host/user configuration.", file=sys.stderr)
        return 1
    argv = [
        "ssh",
        "-i",
        str(credentials / "key"),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=2",
        "-o",
        "UserKnownHostsFile=" + str(credentials / "known_hosts"),
        user + "@" + host,
        'test -d "$HOME/klave-engine" && test -f "$HOME/klave-engine/.env.prod"',
    ]
    if use_ssm:
        proxy = Path(__file__).with_name("ssm_proxy.py")
        argv[1:1] = ["-o", "ProxyCommand=python3 " + shlex.quote(str(proxy))]
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        print(
            "SSH preflight: network/tool unavailable; check approved runner path.", file=sys.stderr
        )
        return 1
    if result.returncode == 0:
        print("SSH transport, authentication and target preflight passed.")
        return 0
    error = result.stderr.lower()
    if "accessdenied" in error or "not authorized" in error or "invalididentitytoken" in error:
        category = "AWS authorization: check approved OIDC trust and deployment permissions"
    elif "targetnotconnected" in error:
        category = "SSM registration: verify the instance agent and instance profile"
    elif "invalid ssm transport configuration" in error:
        category = "SSM configuration: verify the approved instance ID and AWS region"
    elif "resolve hostname" in error:
        category = "DNS: verify configured stable hostname/address"
    elif "host key" in error or "identification has changed" in error:
        category = "host key: compare trusted fingerprint out of band"
    elif "permission denied" in error:
        category = "authentication: verify deploy account and authorized key"
    elif "timed out" in error or "refused" in error or "no route" in error:
        category = "network: inspect instance, routing, firewall and approved runner access"
    else:
        category = "remote target: verify deployment directory and private configuration"
    print("SSH preflight failed — " + category + ". Controls remain enforced.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(
        preflight(
            os.environ.get("EC2_HOST", ""),
            os.environ.get("EC2_USER", "ubuntu"),
            Path(os.environ["RUNNER_TEMP"]) / "klave-ssh",
            use_ssm=os.environ.get("EC2_TRANSPORT") == "ssm",
        )
    )
