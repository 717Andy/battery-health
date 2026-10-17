#!/usr/bin/env python3
"""One-command Hugging Face Space deploy.

Requires HF_TOKEN (write scope) in the environment. This cloud agent does not
have that token, so the Space is packaged but not published from here.

    HF_TOKEN=hf_xxx python scripts/deploy_hf_space.py

Optional:

    HF_SPACE_ID=your-user/battery-health python scripts/deploy_hf_space.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPACE = "717Andy/battery-health"
IGNORE = [
    ".git*",
    ".github/*",
    "**/__pycache__/**",
    "**/*.pyc",
    "**/bin/**",
    "**/obj/**",
    "data/raw/**",
    "data/processed/**",
    "*.mat",
    "src/**",
    "tests/BatteryHealth.Core.Tests/**",
    ".venv/**",
    "venv/**",
]


def main() -> int:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        print(
            "HF_TOKEN is not set. Create a write token at https://huggingface.co/settings/tokens\n"
            "then run:\n\n"
            "  HF_TOKEN=hf_xxx python scripts/deploy_hf_space.py\n",
            file=sys.stderr,
        )
        return 2

    try:
        from huggingface_hub import HfApi, create_repo
    except ImportError:
        print("Install huggingface_hub first:  python -m pip install huggingface_hub", file=sys.stderr)
        return 2

    space_id = os.environ.get("HF_SPACE_ID", DEFAULT_SPACE)
    api = HfApi(token=token)
    url = create_repo(
        space_id,
        repo_type="space",
        space_sdk="docker",
        exist_ok=True,
        private=False,
        token=token,
    )
    api.upload_folder(
        folder_path=str(REPO_ROOT),
        repo_id=space_id,
        repo_type="space",
        ignore_patterns=IGNORE,
    )
    print(f"Uploaded {REPO_ROOT} → {url}")
    print(f"Space URL: https://huggingface.co/spaces/{space_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
