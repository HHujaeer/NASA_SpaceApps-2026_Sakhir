"""CSV access layer.

Files are loaded lazily. Parsed profiles are cached until their CSV or metadata
changes, and callers receive isolated copies. Cell values are read as text and
returned exactly as written (whitespace trimmed). Blank / "N/A"-style cells become
null. Missing data is never filled in or estimated.

Row references: ``row_number`` is the 1-based position of the record among the
data rows of the file (header excluded).
"""
from __future__ import annotations

import os
import json
from copy import deepcopy
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pandas as pd

import config as cfg


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #
class DataError(Exception):
    """Base class for data problems."""


class InvestigationNotFound(DataError):
    pass


class InvestigationExists(DataError):
    """An investigation with this id already exists (maps to HTTP 409)."""


class DataFileError(DataError):
    """File exists but cannot be read as a usable CSV."""


class InvalidRequest(ValueError):
    """The caller supplied invalid input (maps to HTTP 400)."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
MISSING_TOKENS = {"", "na", "n/a", "#n/a", "nan", "null", "none", "-", "--", "---", "?", "missing"}
_NUM_RE = re.compile(r"^\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*([%A-Za-z/°µ]*)\s*$")

PRESSURE_TO_KPA = {"kpa": 1.0, "pa": 0.001, "mpa": 1000.0, "psi": 6.894757, "psia": 6.894757,
                   "atm": 101.325, "bar": 100.0, "mbar": 0.1, "torr": 0.133322, "mmhg": 0.133322}
OXYGEN_TO_PCT = {"%": 1.0, "pct": 1.0, "percent": 1.0, "vol%": 1.0, "fraction": 100.0, "frac": 100.0}
GRAVITY_TO_G = {"g": 1.0, "gs": 1.0}
_UNIT_TABLES = {"pressure": PRESSURE_TO_KPA, "oxygen": OXYGEN_TO_PCT, "gravity": GRAVITY_TO_G}
_NORMALIZED_UNIT = {"pressure": "kPa", "oxygen": "%", "gravity": "g"}
NUMERIC_FIELDS = ("oxygen", "pressure", "flow", "gravity")
CATEGORICAL_FIELDS = ("material", "sensors", "objective", "mission", "source", "findings", "notes", "name")
MAX_DISTINCT = 20
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _norm(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


def _clean_cell(value):
    if not isinstance(value, str):
        return None if value is None or pd.isna(value) else value
    s = value.strip()
    return None if s.lower() in MISSING_TOKENS else s


@lru_cache(maxsize=1024)
def _kw_regex(kw):
    kw = kw.lower().strip()
    if kw[:1].isdigit():
        return re.compile(r"(?<![\d.])" + re.escape(kw) + r"(?!\d|\.\d)")
    if kw.endswith("*"):
        return re.compile(r"(?<![a-z0-9])" + re.escape(kw[:-1]))
    return re.compile(r"(?<![a-z0-9])" + re.escape(kw) + r"(?:s|es)?(?![a-z0-9])")


def match_keywords(text, keywords):
    """Return the keywords (config syntax) that occur in ``text``."""
    text = (text or "").lower()
    return [kw for kw in keywords if _kw_regex(kw).search(text)]


def _numeric_info(values):
    """-> (floats-or-None list, column_is_numeric, most common unit suffix)."""
    nums, units, non_missing, parsed = [], [], 0, 0
    for v in values:
        if v is None:
            nums.append(None)
            continue
        non_missing += 1
        m = _NUM_RE.match(v)
        if m:
            parsed += 1
            nums.append(float(m.group(1)))
            if m.group(2):
                units.append(m.group(2).lower())
        else:
            nums.append(None)
    is_numeric = non_missing > 0 and parsed / non_missing >= 0.8
    unit = Counter(units).most_common(1)[0][0] if units else None
    return nums, is_numeric, unit


def _detect_unit(field, column, value_unit):
    table = _UNIT_TABLES.get(field)
    if not table:
        return None, None
    for token in re.split(r"[^a-z0-9%]+", str(column).lower()):
        if token in table:
            return token, "header"
    if value_unit in table:
        return value_unit, "values"
    return None, None


def _stats(nums):
    vals = [n for n in nums if n is not None]
    if not vals:
        return None
    return {"count": len(vals), "min": min(vals), "max": max(vals), "mean": sum(vals) / len(vals)}


def _distinct(values, limit=MAX_DISTINCT):
    seen = list(dict.fromkeys(v for v in values if v is not None))
    return seen[:limit], len(seen)


def detect_fields(columns):
    """Map logical fields (oxygen, pressure, ...) to actual column names."""
    normed = {c: _norm(c) for c in columns}
    mapping, used = {}, set()
    for field, aliases in cfg.FIELD_ALIASES.items():
        for alias in aliases:
            hit = next((c for c, n in normed.items()
                        if c not in used and f"_{alias}_" in f"_{n}_"), None)
            if hit:
                mapping[field] = hit
                used.add(hit)
                break
    return mapping


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
class CsvService:
    def __init__(self, config):
        self.config = config
        self.data_dir = Path(config.DATA_DIR)
        self._cached_load = lru_cache(maxsize=32)(self._load_version)

    # -- files ----------------------------------------------------------- #
    def _file_map(self):
        if not self.data_dir.is_dir():
            return {}
        files = {}
        for p in sorted(self.data_dir.iterdir()):
            if p.is_file() and p.suffix.lower() == ".csv" and p.stem not in files:
                files[p.stem] = p
        return files

    def data_dir_exists(self):
        return self.data_dir.is_dir()

    def list_investigation_ids(self):
        return list(self._file_map())

    def _path(self, inv_id):
        # Looked up in the directory listing, never built from user input
        path = self._file_map().get(inv_id)
        if path is None:
            raise InvestigationNotFound(f"No investigation with id '{inv_id}'.")
        return path

    # -- reading --------------------------------------------------------- #
    def load_dataframe(self, inv_id):
        """Read one CSV. Returns (DataFrame, info). Index = 1-based row number."""
        path = self._path(inv_id)
        skipped, df = [], None
        for encoding in ("utf-8-sig", "latin-1"):
            skipped.clear()
            try:
                df = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False,
                                 encoding=encoding, engine="python", skipinitialspace=True,
                                 on_bad_lines=lambda line: skipped.append(1))
                break
            except UnicodeDecodeError:
                continue
            except pd.errors.EmptyDataError:
                raise DataFileError(f"'{path.name}' is empty.") from None
            except (pd.errors.ParserError, OSError) as exc:
                raise DataFileError(f"'{path.name}' could not be parsed: {exc}") from None
        if df is None:
            raise DataFileError(f"'{path.name}' has an unsupported text encoding.")

        df.columns = [str(c).strip() or f"column_{i + 1}" for i, c in enumerate(df.columns)]
        for col in df.columns:  # object dtype so missing cells stay None (pandas 3 would use NaN)
            df[col] = pd.Series([_clean_cell(v) for v in df[col].tolist()], index=df.index, dtype=object)
        df.index = range(1, len(df) + 1)  # row_number, assigned before dropping blank rows
        df = df[df.notna().any(axis=1)]
        if df.empty:
            raise DataFileError(f"'{path.name}' has a header but no data rows.")
        return df, {"path": path, "skipped_malformed_rows": len(skipped)}

    def load(self, inv_id):
        """Reuse parsing/profiling until CSV or metadata changes; isolate caller mutations."""
        path = self._path(inv_id)
        files = (path, path.with_suffix(".json"))
        signature = tuple((p.stat().st_mtime_ns, p.stat().st_size) if p.exists() else None for p in files)
        profile, df = self._cached_load(inv_id, signature)
        return deepcopy(profile), df.copy()

    def _load_version(self, inv_id, signature):
        return self._load_uncached(inv_id)

    def _load_uncached(self, inv_id):
        """Read and profile a new source-file version."""
        df, info = self.load_dataframe(inv_id)
        profile = self._profile(inv_id, df, info)
        sidecar = info["path"].with_suffix(".json")
        if sidecar.exists():
            artifact = json.loads(sidecar.read_text(encoding="utf-8"))
            profile["name"] = artifact["name"]
            profile["metadata"] = artifact["metadata"]
            profile["chunk_count"] = artifact["chunk_count"]
            profile["findings"] = artifact.get("findings", [])
            profile["documents"] = artifact.get("documents", [])
            profile["data_notes"] = artifact.get("data_notes", [])
            profile["table_notes"] = artifact.get("table_notes", [])
            profile["source_references"]["values"] = artifact["source_references"]
            profile["_text"] += " " + json.dumps(artifact["metadata"]).lower()
            mapping = {"objective": "Comment[Objective]", "mission": "Comment[Flight Platform]"}
            for field, key in mapping.items():
                if field not in profile["conditions"] and artifact["metadata"].get(key):
                    profile["conditions"][field] = {"type": "categorical", "values": artifact["metadata"][key]}
        return profile, df

    def build_profile(self, inv_id):
        return self.load(inv_id)[0]

    # -- profiling ------------------------------------------------------- #
    def _profile(self, inv_id, df, info):
        path = info["path"]
        columns = list(df.columns)
        fields = detect_fields(columns)
        parsed = {c: _numeric_info(df[c].tolist()) for c in columns}

        conditions, norm_values = {}, {}
        for field, col in fields.items():
            values = df[col].tolist()
            nums, is_num, value_unit = parsed[col]
            if field in NUMERIC_FIELDS and is_num:
                conditions[field], norm = self._numeric_condition(field, col, values, nums, value_unit)
                if norm:
                    norm_values[field] = norm
            elif field in NUMERIC_FIELDS or field in CATEGORICAL_FIELDS:
                cond, norm = self._categorical_condition(field, col, values)
                conditions[field] = cond
                if norm:
                    norm_values[field] = norm

        condition_cols = {fields[f] for f in NUMERIC_FIELDS if f in fields}
        measurements = {}
        for col in columns:
            nums, is_num, _unit = parsed[col]
            tokens = set(_norm(col).split("_"))
            if any(n is not None for n in nums) and col not in condition_cols and not (tokens & cfg.ID_LIKE_TOKENS) \
                    and col not in fields.values() and not ("#" in col and "test" in tokens):
                measurements[col] = _stats(nums)

        total = len(df) * len(columns)
        missing_by_col = {c: int(df[c].isna().sum()) for c in columns if df[c].isna().any()}
        missing = sum(missing_by_col.values())

        names = conditions.get("name", {}).get("values") or []
        refs = conditions.get("source", {}).get("values") or []

        text_parts = [inv_id, " ".join(columns)]
        for col in columns:
            if not parsed[col][1]:
                text_parts.extend(_distinct(df[col].tolist(), 200)[0])

        return {
            "id": inv_id,
            "file": path.name,
            "name": names[0] if len(names) == 1 else inv_id,
            "row_count": len(df),
            "column_count": len(columns),
            "columns": columns,
            "detected_fields": fields,
            "conditions": conditions,
            "measurements": measurements,
            "data_quality": {
                "completeness": round(1 - missing / total, 4) if total else None,
                "missing_cells": missing,
                "total_cells": total,
                "columns_with_missing": missing_by_col,
                "skipped_malformed_rows": info["skipped_malformed_rows"],
            },
            "source_references": {"file": path.name, "values": refs[:10]},
            "last_modified": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "_text": " ".join(text_parts).lower(),
            "_norm_values": norm_values,
        }

    @staticmethod
    def _numeric_condition(field, col, values, nums, value_unit):
        unit, unit_source = _detect_unit(field, col, value_unit)
        stats = _stats(nums)
        cond = {"column": col, "type": "numeric", "min": stats["min"], "max": stats["max"],
                "count": stats["count"], "missing_count": sum(v is None for v in values),
                "distinct_values": _distinct(values)[0], "unit": unit, "unit_source": unit_source,
                "normalized": None}
        norm = None
        factor = _UNIT_TABLES.get(field, {}).get(unit)
        if factor is not None:
            norm = [n * factor for n in nums if n is not None]
            cond["normalized"] = {"unit": _NORMALIZED_UNIT[field], "min": min(norm), "max": max(norm)}
        return cond, norm

    @staticmethod
    def _categorical_condition(field, col, values):
        if field == "sensors":
            items = [p.strip() for v in values if v is not None for p in re.split(r"[;|,]", v) if p.strip()]
        else:
            items = [v for v in values if v is not None]
        distinct, n = _distinct(items)
        cond = {"column": col, "type": "categorical", "values": distinct, "distinct_count": n,
                "missing_count": sum(v is None for v in values), "normalized": None}
        norm = None
        if field == "gravity":  # text such as "microgravity" -> g, only when clearly recognised
            g = [CsvService._gravity_from_text(v) for v in values if v is not None]
            g = [x for x in g if x is not None]
            if g:
                norm = g
                cond["normalized"] = {"unit": "g", "min": min(g), "max": max(g), "basis": "text_keywords"}
        return cond, norm

    @staticmethod
    def _gravity_from_text(text):
        low = text.lower()
        for kw, g in cfg.GRAVITY_TEXT_KEYWORDS:
            if kw in low:
                return g
        return None

    @staticmethod
    def public(profile):
        return {k: v for k, v in profile.items() if not k.startswith("_")}

    # -- records ---------------------------------------------------------- #
    @staticmethod
    def record(df, row_number, profile):
        source_col = profile["detected_fields"].get("source")
        row = df.loc[row_number]
        values = {c: (None if pd.isna(row[c]) else row[c]) for c in df.columns}
        return {
            "row_number": int(row_number),
            "values": values,
            "source": {"file": profile["file"], "row_number": int(row_number),
                       "source_reference": values.get(source_col) if source_col else None},
        }

    # -- API-level operations ---------------------------------------------- #
    def list_investigations(self, q=None, fuel=None, sensor=None, ranges=None,
                            sort="id", order="asc", limit=None, offset=0):
        """Search / filter / sort investigations. Returns (items, total, errors)."""
        ranges = ranges or {}
        if sort not in ("id", "name", "row_count", "completeness"):
            raise InvalidRequest("sort must be one of: id, name, row_count, completeness")
        if order not in ("asc", "desc"):
            raise InvalidRequest("order must be 'asc' or 'desc'")
        terms = re.findall(r"[a-z0-9.]+", (q or "").lower())

        items, errors = [], []
        for inv_id in self.list_investigation_ids():
            try:
                p = self.build_profile(inv_id)
            except DataError as exc:
                errors.append({"id": inv_id, "error": str(exc)})
                continue
            if terms and not all(match_keywords(p["_text"], [t]) or t in p["_text"] for t in terms):
                continue
            cond = p["conditions"]
            if fuel and not any(fuel.lower() in str(v).lower() for v in cond.get("material", {}).get("values", [])):
                continue
            if sensor and not any(sensor.lower() in str(v).lower() for v in cond.get("sensors", {}).get("values", [])):
                continue
            if not all(self._range_ok(p, field, lo, hi) for field, (lo, hi) in ranges.items()):
                continue
            items.append(p)

        keyfn = {"id": lambda p: p["id"].lower(), "name": lambda p: str(p["name"]).lower(),
                 "row_count": lambda p: p["row_count"],
                 "completeness": lambda p: p["data_quality"]["completeness"] or 0}[sort]
        items.sort(key=keyfn, reverse=(order == "desc"))
        total = len(items)
        end = None if limit is None else offset + limit
        return [self.public(p) for p in items[offset:end]], total, errors

    @staticmethod
    def _range_ok(profile, field, lo, hi):
        """Overlap test on unit-normalised values; unknown values cannot match."""
        norm = (profile["conditions"].get(field) or {}).get("normalized")
        if not norm:
            return False
        return (lo is None or norm["max"] >= lo) and (hi is None or norm["min"] <= hi)

    def get_investigation(self, inv_id, include_records=False, limit=100, offset=0):
        profile, df = self.load(inv_id)
        data = self.public(profile)
        if include_records:
            rows = list(df.index)[offset:offset + limit]
            data["records"] = [self.record(df, r, profile) for r in rows]
            data["records_total"] = len(df)
        return data

    # -- writing ------------------------------------------------------------ #
    @staticmethod
    def id_from_filename(filename):
        """Turn an uploaded file name into a safe investigation id (may be empty)."""
        stem = Path(filename or "").stem
        return re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_-")[:64]

    def add_investigation(self, inv_id, content, overwrite=False):
        """Validate an uploaded CSV and store it as ``<inv_id>.csv`` in the data directory.

        The upload is parsed in a scratch directory first, so an unreadable file never
        reaches the data directory. Replacing an existing investigation needs ``overwrite``.
        """
        if not isinstance(inv_id, str) or not ID_RE.match(inv_id):
            raise InvalidRequest("'id' must be 1-64 characters: letters, digits, '_' or '-', "
                                 "starting with a letter or digit.")
        if not content or not content.strip():
            raise InvalidRequest("The uploaded file is empty.")
        limit = getattr(self.config, "MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
        if len(content) > limit:
            raise InvalidRequest(f"The uploaded file is larger than the {limit}-byte limit.")
        existing = self._file_map().get(inv_id)
        if existing and not overwrite:
            raise InvestigationExists(f"An investigation with id '{inv_id}' already exists. "
                                      "Choose another id or set overwrite=true.")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / f"{inv_id}.csv").write_bytes(content)
            CsvService(cfg.Config(env={}, DATA_DIR=tmp)).build_profile(inv_id)  # raises DataFileError
        self.data_dir.mkdir(parents=True, exist_ok=True)
        dest = existing or self.data_dir / f"{inv_id}.csv"
        staging = self.data_dir / f".{inv_id}.upload"  # not *.csv, so never listed
        try:
            staging.write_bytes(content)
            os.replace(staging, dest)
            dest.with_suffix(".json").unlink(missing_ok=True)
            dest.with_suffix(".chunks.json").unlink(missing_ok=True)
        finally:
            staging.unlink(missing_ok=True)
        return self.get_investigation(inv_id), existing is not None

    def delete_investigation(self, inv_id):
        path = self._path(inv_id)  # raises InvestigationNotFound
        path.unlink()
        path.with_suffix(".json").unlink(missing_ok=True)
        path.with_suffix(".chunks.json").unlink(missing_ok=True)
        return {"id": inv_id, "file": path.name, "deleted": True}

    def statistics(self):
        """Aggregate statistics across all files (each file read on demand)."""
        profiles, errors = [], []
        for inv_id in self.list_investigation_ids():
            try:
                profiles.append(self.build_profile(inv_id))
            except DataError as exc:
                errors.append({"id": inv_id, "error": str(exc)})

        def collect(field):
            c = Counter()
            for p in profiles:
                for v in p["conditions"].get(field, {}).get("values", []):
                    c[v] += 1
            return [{"value": v, "investigations": n} for v, n in c.most_common()]

        ranges = {}
        for field in ("oxygen", "pressure", "gravity"):
            norms = [p["conditions"][field]["normalized"] for p in profiles
                     if p["conditions"].get(field, {}).get("normalized")]
            if norms:
                ranges[field] = {"unit": norms[0]["unit"], "min": min(n["min"] for n in norms),
                                 "max": max(n["max"] for n in norms), "investigations": len(norms)}
        completeness = [p["data_quality"]["completeness"] for p in profiles
                        if p["data_quality"]["completeness"] is not None]
        return {
            "data_directory_exists": self.data_dir_exists(),
            "investigation_count": len(profiles),
            "unreadable_files": errors,
            "total_records": sum(p["row_count"] for p in profiles),
            "average_completeness": round(sum(completeness) / len(completeness), 4) if completeness else None,
            "materials": collect("material"),
            "sensors": collect("sensors"),
            "condition_ranges_normalized": ranges,
            "per_investigation": [{"id": p["id"], "name": p["name"], "row_count": p["row_count"],
                                   "completeness": p["data_quality"]["completeness"]} for p in profiles],
        }
