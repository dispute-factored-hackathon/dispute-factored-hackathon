"""Update deploy-time AWS secrets from a local .env without printing their values."""

from __future__ import annotations

import argparse
import json
import os
import subprocess

from dotenv import load_dotenv


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True)
    parser.add_argument("--motherduck-secret-arn", required=True)
    args = parser.parse_args()
    load_dotenv()
    token = os.environ.get("MOTHERDUCK_TOKEN", "").strip()
    if not token:
        print("MOTHERDUCK_TOKEN is not local; retaining the existing AWS secret.")
        return 0
    subprocess.run(
        [
            "aws",
            "secretsmanager",
            "put-secret-value",
            "--region",
            args.region,
            "--secret-id",
            args.motherduck_secret_arn,
            "--secret-string",
            "file:///dev/stdin",
            "--no-cli-pager",
        ],
        input=json.dumps({"MOTHERDUCK_TOKEN": token}),
        text=True,
        stdout=subprocess.DEVNULL,
        check=True,
    )
    print("MotherDuck runtime secret updated without exposing its value.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
