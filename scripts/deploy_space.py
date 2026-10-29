"""Upload the web app to the Hugging Face Space.

Log in once in your own terminal (the token stays on your machine, never in chat or in git):
  .venv\\Scripts\\hf auth login
Then:
  .venv\\Scripts\\python scripts/deploy_space.py

Only what the Space runs is uploaded: app.py, the actsprite package, the showcase, requirements, licence,
and space/README.md as the Space card. Videos, caches, logs and .env never leave this machine.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi
from huggingface_hub.errors import HfHubHTTPError

ROOT = Path(__file__).resolve().parent.parent
SPACE_ID = "Andy0730huggin/actsprite"
FILES = ["app.py", "requirements.txt", "LICENSE"]
DIRS = ["actsprite", "showcase"]


def main() -> None:
    api = HfApi()
    try:
        user = api.whoami()["name"]
    except (HfHubHTTPError, OSError, KeyError):
        sys.exit("Not logged in to Hugging Face. Run: .venv\\Scripts\\hf auth login  (token with write access)")
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True).stdout.strip()  # noqa: E731
    sha = git("rev-parse", "--short", "HEAD")
    if sha and git("status", "--porcelain"):
        sha += " + uncommitted changes"
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        for f in FILES:
            shutil.copy2(ROOT / f, stage / f)
        for d in DIRS:
            shutil.copytree(ROOT / d, stage / d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copy2(ROOT / "space" / "README.md", stage / "README.md")
        info = api.upload_folder(
            folder_path=stage,
            repo_id=SPACE_ID,
            repo_type="space",
            commit_message=f"Deploy from GitHub {sha or 'working tree'}",
            delete_patterns=[f"{d}/**" for d in DIRS],  # drop files removed locally
        )
    print(f"Uploaded as {user}: {info.commit_url}")
    print(f"Build logs: https://huggingface.co/spaces/{SPACE_ID}?logs=build")


if __name__ == "__main__":
    main()
