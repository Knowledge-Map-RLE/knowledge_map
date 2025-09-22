#!/usr/bin/env python3
"""
Warm Hugging Face cache for Docling models to enable offline usage.
"""
import os
from pathlib import Path
from huggingface_hub import snapshot_download

def main() -> None:
    repo_id = os.getenv("DOCLING_MODELS_REPO", "ds4sd/docling-models")
    revision = os.getenv("DOCLING_MODELS_REVISION", "v2.0.0")
    cache_dir = Path(os.getenv("HF_HOME", os.getenv("HF_HUB_CACHE", str((Path(__file__).resolve().parents[1] / "model_cache").absolute()))))
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Ensure environment is aware of cache location (standard HF structure)
    os.environ["HF_HOME"] = str(cache_dir)
    os.environ["HF_HUB_CACHE"] = str(cache_dir)
    # Optionally honor custom endpoint
    hf_endpoint = os.getenv("DOC_LING_HF_ENDPOINT")
    if hf_endpoint:
        os.environ["HF_ENDPOINT"] = hf_endpoint
    # Disable hf_transfer fast-path to avoid extra dependency
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"

    print(f"Warming cache into: {cache_dir}")
    # Warm into standard HF cache (no local_dir) so offline resolution works
    snapshot_download(repo_id, revision=revision)
    print("Cache warmed successfully.")

if __name__ == "__main__":
    main()


