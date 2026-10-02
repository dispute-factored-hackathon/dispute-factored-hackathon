"""Write an ephemeral Docker ECR auth file without a credential helper."""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: write_docker_auth.py CONFIG_PATH REGISTRY")
    password = sys.stdin.read().strip()
    if not password:
        raise SystemExit("ECR password was empty")
    config_path = Path(sys.argv[1])
    registry = sys.argv[2]
    encoded = base64.b64encode(f"AWS:{password}".encode()).decode()
    config_path.write_text(json.dumps({"auths": {registry: {"auth": encoded}}}))
    os.chmod(config_path, 0o600)


if __name__ == "__main__":
    main()
