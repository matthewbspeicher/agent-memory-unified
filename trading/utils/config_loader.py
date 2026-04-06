"""Centralized YAML config loading with path resolution and caching."""

from __future__ import annotations

import os
import pathlib
from typing import Any

import yaml


class ConfigLoader:
    """Resolves and caches YAML config files."""

    def __init__(
        self,
        app_root: pathlib.Path | str | None = None,
        docker_root: str = "/app",
    ) -> None:
        self._app_root = (
            pathlib.Path(app_root)
            if app_root
            else pathlib.Path(__file__).resolve().parent.parent
        )
        self._docker_root = docker_root
        self._cache: dict[str, Any] = {}

    def resolve(self, name: str) -> str | None:
        """Find a config file by name, searching Docker root, CWD, app root, and repo root."""
        candidates = [
            os.path.join(self._docker_root, name),
            name,
            str(self._app_root / name),
            str(self._app_root.parent / name),
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
        return None

    def load_yaml(self, name: str) -> Any:
        """Load and cache a YAML file. Returns None if not found."""
        if name in self._cache:
            return self._cache[name]
        path = self.resolve(name)
        if path is None:
            return None
        with open(path) as f:
            data = yaml.safe_load(f)
        self._cache[name] = data
        return data
