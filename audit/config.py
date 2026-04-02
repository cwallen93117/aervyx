from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)

API_BASE_URL: str = os.getenv("AERVYX_API_URL", "https://api.aervyx.net")
API_USERNAME: str = os.getenv("AERVYX_USERNAME", "")
API_PASSWORD: str = os.getenv("AERVYX_PASSWORD", "")

HIGHLAND_ROOT = Path(
    os.getenv(
        "HIGHLAND_ROOT",
        r"C:\Users\Charles\Documents\3. Flying\Hang Gliding\$ Highland Challenge Files",
    )
)

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
