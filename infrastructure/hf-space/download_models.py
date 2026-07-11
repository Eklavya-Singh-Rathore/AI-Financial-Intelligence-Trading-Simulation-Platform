"""Build-time model bake.

Downloads the official checkpoints from the Hugging Face Hub into the image's
HF cache (HF_HOME) so that container starts/wakes never touch the network and
no weights are committed to the Space repo. All three repos are public (MIT /
Apache-2.0), so no token is needed at build time.
"""

from __future__ import annotations

import os

from huggingface_hub import snapshot_download

_REPOS = (
    ("KRONOS_MODEL_ID", "NeoQuasar/Kronos-small"),
    ("KRONOS_TOKENIZER_ID", "NeoQuasar/Kronos-Tokenizer-base"),
    ("EMBEDDING_MODEL_ID", "sentence-transformers/all-MiniLM-L6-v2"),
)


def main() -> None:
    for env_name, default in _REPOS:
        repo_id = os.environ.get(env_name) or default
        print(f"[download_models] fetching {repo_id} ...", flush=True)
        path = snapshot_download(repo_id)
        print(f"[download_models] cached at {path}", flush=True)


if __name__ == "__main__":
    main()
