"""Import/export strategies — swap formats without branching in views."""

from __future__ import annotations

import csv
import io
import json
from abc import ABC, abstractmethod
from typing import Any, Iterable


class DataExportStrategy(ABC):
    content_type: str
    extension: str

    @abstractmethod
    def export(self, rows: Iterable[dict[str, Any]], *, fieldnames: list[str] | None = None) -> bytes:
        ...


class JsonExportStrategy(DataExportStrategy):
    content_type = "application/json"
    extension = "json"

    def export(self, rows: Iterable[dict[str, Any]], *, fieldnames: list[str] | None = None) -> bytes:
        data = list(rows)
        if fieldnames:
            data = [{k: row.get(k) for k in fieldnames} for row in data]
        return json.dumps(data, default=str, indent=2).encode()


class CsvExportStrategy(DataExportStrategy):
    content_type = "text/csv"
    extension = "csv"

    def export(self, rows: Iterable[dict[str, Any]], *, fieldnames: list[str] | None = None) -> bytes:
        rows = list(rows)
        if not rows and not fieldnames:
            return b""
        names = fieldnames or list(rows[0].keys())
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=names, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in names})
        return buf.getvalue().encode()


_EXPORT: dict[str, DataExportStrategy] = {
    "json": JsonExportStrategy(),
    "csv": CsvExportStrategy(),
}


def get_export_strategy(fmt: str) -> DataExportStrategy:
    key = (fmt or "json").lower().strip()
    if key not in _EXPORT:
        raise ValueError(f"unsupported export format: {fmt}")
    return _EXPORT[key]


class DataImportStrategy(ABC):
    @abstractmethod
    def parse(self, raw: bytes | str) -> list[dict[str, Any]]:
        ...


class JsonImportStrategy(DataImportStrategy):
    def parse(self, raw: bytes | str) -> list[dict[str, Any]]:
        text = raw.decode() if isinstance(raw, bytes) else raw
        data = json.loads(text or "[]")
        if isinstance(data, dict):
            data = data.get("results") or data.get("items") or [data]
        if not isinstance(data, list):
            raise ValueError("JSON import must be a list or {results: [...]}")
        return [row for row in data if isinstance(row, dict)]


class CsvImportStrategy(DataImportStrategy):
    def parse(self, raw: bytes | str) -> list[dict[str, Any]]:
        text = raw.decode() if isinstance(raw, bytes) else raw
        reader = csv.DictReader(io.StringIO(text))
        return [dict(row) for row in reader]


_IMPORT: dict[str, DataImportStrategy] = {
    "json": JsonImportStrategy(),
    "csv": CsvImportStrategy(),
}


def get_import_strategy(fmt: str) -> DataImportStrategy:
    key = (fmt or "json").lower().strip()
    if key not in _IMPORT:
        raise ValueError(f"unsupported import format: {fmt}")
    return _IMPORT[key]
