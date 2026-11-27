"""Configuration for portable-memory.

All settings come from environment variables with sensible defaults so the
project runs immediately after clone with no config file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Config:
    data_dir: Path
    db_path: Path
    host: str
    port: int
    token: str
    decay_half_life_days: float
    default_limit: int
    max_limit: int

    @classmethod
    def from_env(cls) -> "Config":
        data_dir = Path(
            os.environ.get(
                "PMEM_DATA_DIR",
                str(Path.home() / ".portable-memory"),
            )
        ).expanduser()
        return cls(
            data_dir=data_dir,
            db_path=data_dir / "memory.sqlite3",
            host=os.environ.get("PMEM_HOST", "127.0.0.1"),
            port=_env_int("PMEM_PORT", 8765),
            token=os.environ.get("PMEM_TOKEN", ""),
            decay_half_life_days=_env_float("PMEM_HALF_LIFE_DAYS", 30.0),
            default_limit=_env_int("PMEM_DEFAULT_LIMIT", 8),
            max_limit=_env_int("PMEM_MAX_LIMIT", 50),
        )

    def ensure_data_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
