"""Where case files are kept: a local folder now, Azure Blob Storage once dev access is in place.

Both stores have the same methods, so the pipeline does not change when we switch.
Areas used: cases (raw, UNMASKED), tokens (token maps, sensitive), masked, results, review.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from .settings import Settings


class Store(Protocol):
    def put(self, use_case: str, area: str, name: str, obj: Any) -> str: ...
    def get(self, use_case: str, area: str, name: str) -> Any: ...
    def list(self, use_case: str, area: str) -> list[str]: ...


class LocalStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, use_case: str, area: str, name: str) -> Path:
        return self.root / use_case / area / name

    def put(self, use_case: str, area: str, name: str, obj: Any) -> str:
        p = self._path(use_case, area, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
        return str(p)

    def get(self, use_case: str, area: str, name: str) -> Any:
        return json.loads(self._path(use_case, area, name).read_text(encoding="utf-8"))

    def list(self, use_case: str, area: str) -> list[str]:
        d = self.root / use_case / area
        return sorted(p.name for p in d.glob("*.json") if not p.name.startswith("_")) if d.exists() else []


class BlobStore:
    """One container per use case and area, e.g. alessa-cases, alessa-masked. Uses the pod's / developer's
    Entra identity (Storage Blob Data Contributor), no keys."""

    def __init__(self, account_url: str):
        from azure.identity import DefaultAzureCredential  # installed from requirements-azure.txt
        from azure.storage.blob import BlobServiceClient
        self.svc = BlobServiceClient(account_url, credential=DefaultAzureCredential())

    def _container(self, use_case: str, area: str):
        return self.svc.get_container_client(f"{use_case}-{area}".lower())

    def put(self, use_case: str, area: str, name: str, obj: Any) -> str:
        c = self._container(use_case, area)
        c.upload_blob(name, json.dumps(obj, default=str).encode("utf-8"), overwrite=True)
        return f"{c.container_name}/{name}"

    def get(self, use_case: str, area: str, name: str) -> Any:
        return json.loads(self._container(use_case, area).download_blob(name).readall())

    def list(self, use_case: str, area: str) -> list[str]:
        return sorted(b.name for b in self._container(use_case, area).list_blobs() if b.name.endswith(".json"))


def get_store(s: Settings) -> Store:
    if s.storage == "blob":
        return BlobStore(s.blob_account_url)
    return LocalStore(s.data_dir)
