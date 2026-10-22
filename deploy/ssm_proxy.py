"""SSH ProxyCommand: authenticate to the one approved SSM SSH document."""

import os
import re
import sys


def main() -> int:
    instance = os.environ.get("EC2_INSTANCE_ID", "")
    region = os.environ.get("AWS_REGION", "")
    if not re.fullmatch(r"i-[0-9a-f]{17}", instance) or not re.fullmatch(
        r"[a-z]{2}(?:-[a-z]+)+-\d", region
    ):
        print("Invalid SSM transport configuration; no public SSH fallback.", file=sys.stderr)
        return 2
    try:
        os.execvp(
            "aws",
            [
                "aws",
                "ssm",
                "start-session",
                "--target",
                instance,
                "--region",
                region,
                "--document-name",
                "Klave-DeploymentSSH",
            ],
        )
    except OSError:
        print("AWS CLI unavailable; no public SSH fallback.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
