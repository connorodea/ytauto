"""Generic JSON file persistence for Pydantic models."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


class JsonDirectoryStore(Generic[ModelT]):
    """Persist Pydantic models as individual JSON files in a directory.

    Each model must have an ``id`` attribute used as the filename stem.
    Writes are atomic (write to temp file, then rename).
    """

    def __init__(self, directory: Path, model_type: type[ModelT]) -> None:
        self.directory = directory
        self.model_type = model_type
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, model: ModelT) -> ModelT:
        """Persist *model* to ``<id>.json``, atomically."""
        identifier = getattr(model, "id")
        target = self.directory / f"{identifier}.json"
        fd, tmp = tempfile.mkstemp(dir=self.directory, suffix=".tmp")
        try:
            with open(fd, "w", encoding="utf-8") as f:
                f.write(model.model_dump_json(indent=2))
            Path(tmp).rename(target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return model

    def get(self, identifier: str) -> ModelT:
        """Load a model by *identifier*. Raises FileNotFoundError if missing."""
        path = self.directory / f"{identifier}.json"
        if not path.exists():
            raise FileNotFoundError(f"No record found: {identifier}")
        raw = path.read_text(encoding="utf-8")
        return self.model_type.model_validate_json(raw)

    def list_all(self) -> list[ModelT]:
        """Return all persisted models, sorted by created_at descending."""
        items: list[ModelT] = []
        for path in sorted(self.directory.glob("*.json"), reverse=True):
            try:
                raw = path.read_text(encoding="utf-8")
                items.append(self.model_type.model_validate_json(raw))
            except Exception:
                continue
        items.sort(key=lambda m: getattr(m, "created_at", ""), reverse=True)
        return items

    def delete(self, identifier: str) -> bool:
        """Delete a model by *identifier*. Returns True if deleted."""
        path = self.directory / f"{identifier}.json"
        if path.exists():
            path.unlink()
            return True
        return False
