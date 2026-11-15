"""Side-by-side comparison of investigations.

The comparison itself is deterministic and built only from the CSV profiles. An
optional AI explanation is generated from that comparison alone.
"""
from __future__ import annotations

import json
import re

from services.ai_service import AIServiceError
from services.csv_service import DataError, InvalidRequest

RANGE_FIELDS = ["oxygen", "pressure", "flow", "gravity"]
DISCRETE_FIELDS = ["material", "sensors"]
LABELS = {"material": "fuel/material", "sensors": "sensors", "oxygen": "oxygen concentration",
          "pressure": "pressure", "flow": "airflow", "gravity": "gravity"}

EXPLAIN_TASK = ("Explain the similarities and differences between these experiments using ONLY the comparison "
                "data in the context. Experiments are tagged E1, E2, ... Point out parameters that are not "
                "reported or not comparable instead of assuming values.")


class ComparisonService:
    def __init__(self, config, csv_service, ai_service):
        self.config = config
        self.csv = csv_service
        self.ai = ai_service

    def compare(self, ids, explain=False):
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            raise InvalidRequest("'ids' must be a list of investigation ids.")
        ids = list(dict.fromkeys(ids))
        if not 2 <= len(ids) <= 10:
            raise InvalidRequest("Provide between 2 and 10 distinct investigation ids to compare.")
        profiles = {i: self.csv.build_profile(i) for i in ids}  # raises InvestigationNotFound / DataFileError
        tags = {i: f"E{n}" for n, i in enumerate(ids, 1)}

        similarities, differences, not_available, parameters = [], [], [], {}
        for field in DISCRETE_FIELDS + RANGE_FIELDS:
            entries = {i: profiles[i]["conditions"].get(field) for i in ids}
            missing = [i for i, c in entries.items() if not c]
            for i in missing:
                not_available.append(f"{LABELS[field]} is not reported in {profiles[i]['name']} ({tags[i]}).")
            present = {i: c for i, c in entries.items() if c}
            if field in DISCRETE_FIELDS:
                result = self._compare_discrete(field, present, tags)
            else:
                result = self._compare_range(field, present, tags)
            result["per_investigation"] = {tags[i]: self._brief(c) for i, c in present.items()}
            parameters[field] = result
            (similarities if result.get("similar") else differences if result.get("different") else []
             ).append(result["summary"])
            if result["status"] in ("not_comparable", "insufficient_data"):
                not_available.append(result["summary"])

        results = self._compare_results(profiles, tags)
        out = {
            "investigations": [{"tag": tags[i], "id": i, "name": profiles[i]["name"], "file": profiles[i]["file"],
                                "row_count": profiles[i]["row_count"]} for i in ids],
            "parameters": parameters,
            "results": results,
            "similarities": similarities,
            "differences": differences,
            "not_available": not_available,
            "note": "All values come from the CSV files; 'not reported' means the file has no usable value.",
        }
        if explain:
            out["explanation"] = self._explain(out)
        return out

    # -- parameter comparison ------------------------------------------------ #
    @staticmethod
    def _brief(c):
        keys = ("column", "type", "min", "max", "unit", "normalized", "values", "distinct_values")
        return {k: c[k] for k in keys if k in c and c[k] not in (None, [])}

    @staticmethod
    def _compare_discrete(field, present, tags):
        label = LABELS[field]
        sets = {i: {str(v).lower(): str(v) for v in c.get("values", [])} for i, c in present.items()}
        if len(present) < 2:
            return {"status": "insufficient_data", "summary": f"{label}: fewer than two experiments report it."}
        shared = set.intersection(*[set(s) for s in sets.values()])
        union = set.union(*[set(s) for s in sets.values()])
        shared_txt = ", ".join(sorted(next(iter(sets.values()))[k] for k in shared)) if shared else ""
        if shared and shared == union:
            return {"status": "identical", "similar": True, "shared": sorted(shared),
                    "summary": f"{label}: identical across experiments ({shared_txt})."}
        parts = [f"{tags[i]}: {', '.join(s.values()) or 'none'}" for i, s in sets.items()]
        return {"status": "different" if not shared else "partial_overlap", "different": True,
                "shared": sorted(shared),
                "summary": f"{label}: differs ({'; '.join(parts)})" + (f"; shared: {shared_txt}." if shared else ".")}

    @staticmethod
    def _compare_range(field, present, tags):
        label = LABELS[field]
        if len(present) < 2:
            return {"status": "insufficient_data", "summary": f"{label}: fewer than two experiments report it."}
        intervals, basis = {}, None
        if all(c.get("normalized") for c in present.values()):
            intervals = {i: (c["normalized"]["min"], c["normalized"]["max"]) for i, c in present.items()}
            basis = "normalised to " + next(iter(present.values()))["normalized"]["unit"]
        else:
            cols = {re.sub(r"[^a-z0-9]+", "_", str(c.get("column", "")).lower()) for c in present.values()}
            units = {c.get("unit") for c in present.values()}
            if all(c.get("type") == "numeric" for c in present.values()) and (
                    len(cols) == 1 or (len(units) == 1 and None not in units)):
                intervals = {i: (c["min"], c["max"]) for i, c in present.items()}
                basis = "raw values as written in the files"
            else:
                return {"status": "not_comparable",
                        "summary": f"{label}: not numerically comparable (unknown or different units / non-numeric values)."}
        lo, hi = max(v[0] for v in intervals.values()), min(v[1] for v in intervals.values())
        text = "; ".join(f"{tags[i]}: {v[0]:g}–{v[1]:g}" for i, v in intervals.items())
        if len({v for v in intervals.values()}) == 1:
            return {"status": "identical", "similar": True, "basis": basis,
                    "summary": f"{label}: identical range ({text}; {basis})."}
        if lo <= hi:
            return {"status": "overlapping", "similar": True, "basis": basis, "overlap": [lo, hi],
                    "summary": f"{label}: ranges overlap between {lo:g} and {hi:g} ({text}; {basis})."}
        return {"status": "disjoint", "different": True, "basis": basis,
                "summary": f"{label}: ranges do not overlap ({text}; {basis})."}

    @staticmethod
    def _compare_results(profiles, tags):
        findings = {tags[i]: p["conditions"]["findings"]["values"]
                    for i, p in profiles.items() if p["conditions"].get("findings", {}).get("values")}
        by_name = {}
        for i, p in profiles.items():
            for col, st in p["measurements"].items():
                if st:
                    by_name.setdefault(re.sub(r"[^a-z0-9]+", "_", col.lower()).strip("_"), {})[tags[i]] = {"column": col, **st}
        total = len(profiles)
        return {
            "findings_text": findings,
            "shared_measurements": {k: v for k, v in by_name.items() if len(v) == total},
            "partial_or_unique_measurements": {k: v for k, v in by_name.items() if len(v) < total},
            "findings_not_reported_for": [tags[i] for i in profiles if tags[i] not in findings],
        }

    # -- AI explanation -------------------------------------------------------- #
    def _explain(self, comparison):
        context = json.dumps({k: comparison[k] for k in ("investigations", "parameters", "results",
                                                         "similarities", "differences", "not_available")},
                             ensure_ascii=False, default=str)
        limit = self.config.MAX_CONTEXT_CHARS
        truncated = len(context) > limit
        try:
            res = self.ai.generate(EXPLAIN_TASK, context[:limit])
        except AIServiceError as exc:
            return {"status": "unavailable", "error": {"code": exc.code, "message": exc.message}}
        return {"status": "ok", "text": res["text"], "provider": res["provider"], "model": res["model"],
                "context_truncated": truncated,
                "label": "AI-generated explanation based only on the comparison data above."}
