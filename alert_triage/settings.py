"""Settings from environment variables (and an optional .env file in the project root).

Local development needs nothing set: files go to ./data and the fake model is used.
Once Azure dev access is in place, set STORAGE=blob and MODEL=apim (see .env.example).
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path = ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


@dataclass(frozen=True)
class Settings:
    storage: str = "local"            # local | blob
    data_dir: str = "data"            # local storage root
    blob_account_url: str = ""        # https://<account>.blob.core.windows.net
    model: str = "fake"               # fake | apim
    apim_endpoint: str = ""           # APIM AI Gateway URL
    apim_key: str = ""                # APIM subscription key (from Key Vault on AKS)
    model_deployment: str = ""        # deployment name in Foundry
    api_version: str = "2024-10-21"


def get_settings() -> Settings:
    _load_dotenv()
    e = os.environ.get
    return Settings(
        storage=e("STORAGE", "local"),
        data_dir=e("DATA_DIR", "data"),
        blob_account_url=e("BLOB_ACCOUNT_URL", ""),
        model=e("MODEL", "fake"),
        apim_endpoint=e("APIM_ENDPOINT", ""),
        apim_key=e("APIM_KEY", ""),
        model_deployment=e("MODEL_DEPLOYMENT", ""),
        api_version=e("OPENAI_API_VERSION", "2024-10-21"),
    )
