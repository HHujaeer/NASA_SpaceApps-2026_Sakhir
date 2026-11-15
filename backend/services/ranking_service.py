"""Application-generated relevance ranking.

Scores are computed from the contents of each CSV with transparent rules; nothing
here is a NASA assessment. Each criterion returns 0..1 plus a plain-language
explanation, and the weighted total is scaled to 0..100.
"""
from __future__ import annotations

import config as cfg
from services.csv_service import DataError, InvalidRequest, match_keywords


def _saturate(count, target):
    return min(1.0, count / target) if target else 0.0


class RankingService:
    def __init__(self, config, csv_service):
        self.config = config
        self.csv = csv_service

    # -- public ------------------------------------------------------------- #
    def categories(self):
        return [{"key": k, "label": v["label"]} for k, v in cfg.CATEGORIES.items()]

    def resolve_weights(self, override=None):
        weights = dict(self.config.RANKING_WEIGHTS)
        if override:
            unknown = set(override) - set(cfg.DEFAULT_WEIGHTS)
            if unknown:
                raise InvalidRequest(f"Unknown weight(s): {sorted(unknown)}. "
                                     f"Valid: {sorted(cfg.DEFAULT_WEIGHTS)}")
            weights.update(override)
        try:
            weights = {k: float(v) for k, v in weights.items()}
        except (TypeError, ValueError):
            raise InvalidRequest("Weights must be numbers.") from None
        if any(v < 0 for v in weights.values()) or sum(weights.values()) <= 0:
            raise InvalidRequest("Weights must be non-negative and not all zero.")
        total = sum(weights.values())
        return {k: v / total for k, v in weights.items()}  # fractions summing to 1

    def rank(self, category, weights=None, limit=None):
        if category not in cfg.CATEGORIES:
            raise InvalidRequest(f"Unknown category '{category}'. Valid: {sorted(cfg.CATEGORIES)}")
        fractions = self.resolve_weights(weights)
        results, errors = [], []
        for inv_id in self.csv.list_investigation_ids():
            try:
                profile = self.csv.build_profile(inv_id)
            except DataError as exc:
                errors.append({"id": inv_id, "error": str(exc)})
                continue
            results.append(self.score_profile(profile, category, fractions))
        results.sort(key=lambda r: (-r["score"], r["id"]))
        for i, r in enumerate(results, 1):
            r["rank"] = i
        if limit:
            results = results[:limit]
        return {
            "category": category,
            "category_label": cfg.CATEGORIES[category]["label"],
            "disclaimer": cfg.RANKING_DISCLAIMER,
            "weights_percent": {k: round(v * 100, 2) for k, v in fractions.items()},
            "reference_environments": {k: v for k, v in cfg.ENV_PROFILES.items()},
            "ranked": results,
            "unreadable_files": errors,
        }

    # -- scoring ------------------------------------------------------------- #
    def score_profile(self, profile, category, fractions):
        cat = cfg.CATEGORIES[category]
        criteria = {
            "mission_relevance": self._mission(profile, cat),
            "fire_safety_relevance": self._fire_safety(profile, cat),
            "data_quality": self._data_quality(profile),
            "environmental_similarity": self._environment(profile, cat),
            "predictive_modeling_value": self._predictive(profile),
        }
        out, total = {}, 0.0
        for name, (score, explanation, details) in criteria.items():
            weighted = score * fractions[name] * 100
            total += weighted
            out[name] = {"score": round(score * 100, 1), "weight_percent": round(fractions[name] * 100, 2),
                         "weighted_points": round(weighted, 2), "explanation": explanation,
                         "details": details}
        return {
            "id": profile["id"], "name": profile["name"], "score": round(total, 1), "criteria": out,
            "supporting_data": {
                "file": profile["file"], "row_count": profile["row_count"],
                "detected_fields": profile["detected_fields"],
                "completeness": profile["data_quality"]["completeness"],
                "source_references": profile["source_references"],
            },
        }

    @staticmethod
    def _mission(p, cat):
        hits = match_keywords(p["_text"], cat["mission_keywords"])
        score = _saturate(len(hits), 2)
        if hits:
            why = f"{len(hits)} mission keyword(s) found in the file's columns/values: {', '.join(hits)}."
        else:
            why = "No mission keywords for this category were found in the file; scored 0 (this reflects missing metadata, not proof of irrelevance)."
        return score, why, {"matched_keywords": hits}

    @staticmethod
    def _fire_safety(p, cat):
        general = match_keywords(p["_text"], cfg.FIRE_KEYWORDS)
        parts = [_saturate(len(general), 4)]
        specific = []
        if cat["safety_keywords"]:
            specific = match_keywords(p["_text"], cat["safety_keywords"])
            parts.append(_saturate(len(specific), 2))
        score = sum(parts) / len(parts)
        why = (f"General fire terms found: {', '.join(general) or 'none'}."
               + (f" Category-specific terms found: {', '.join(specific) or 'none'}." if cat["safety_keywords"] else ""))
        return score, why, {"general_matches": general, "category_matches": specific}

    @staticmethod
    def _data_quality(p):
        dq = p["data_quality"]
        completeness = dq["completeness"] or 0.0
        rows = _saturate(p["row_count"], 30)
        has_source = 1.0 if p["detected_fields"].get("source") else 0.0
        numeric_share = _saturate(len(p["measurements"]) + sum(
            1 for f in ("oxygen", "pressure", "flow", "gravity")
            if p["conditions"].get(f, {}).get("type") == "numeric"), 4)
        malformed_penalty = 0.1 if dq["skipped_malformed_rows"] else 0.0
        score = max(0.0, 0.4 * completeness + 0.2 * rows + 0.2 * has_source + 0.2 * numeric_share - malformed_penalty)
        why = (f"Completeness {completeness:.0%} (40%), {p['row_count']} records vs a 30-record target (20%), "
               f"source-reference column {'present' if has_source else 'absent'} (20%), "
               f"numeric measurement/condition columns (20%)"
               + (f"; penalty for {dq['skipped_malformed_rows']} malformed row(s) skipped." if malformed_penalty else "."))
        return score, why, {"completeness": completeness, "row_count": p["row_count"],
                            "has_source_column": bool(has_source), "measurement_columns": list(p["measurements"])}

    @staticmethod
    def _environment(p, cat):
        norm = p["_norm_values"]
        params = [k for k in ("pressure_kpa", "oxygen_pct", "gravity_g")
                  if norm.get({"pressure_kpa": "pressure", "oxygen_pct": "oxygen", "gravity_g": "gravity"}[k])]
        field_of = {"pressure_kpa": "pressure", "oxygen_pct": "oxygen", "gravity_g": "gravity"}
        if not params:
            return 0.0, ("Pressure, oxygen and gravity could not be assessed (missing values or unknown units); "
                         "scored 0 (not evidence of dissimilarity)."), {"assessable": False}
        best_score, best_name = -1.0, None
        for name in cat["env_profiles"]:
            ref = cfg.ENV_PROFILES[name]
            sims = []
            for param in params:
                values = norm[field_of[param]]
                tol = cfg.ENV_TOLERANCE[param]
                sims.append(sum(max(0.0, 1 - abs(v - ref[param]) / tol) for v in values) / len(values))
            score = sum(sims) / len(sims)
            if score > best_score:
                best_score, best_name = score, name
        ref = cfg.ENV_PROFILES[best_name]
        why = (f"Closest reference environment: {ref['label']}. Compared parameters: {', '.join(params)} "
               f"(unit-normalised). Reference values are configurable assumptions.")
        return best_score, why, {"assessable": True, "compared_parameters": params, "reference": best_name}

    @staticmethod
    def _predictive(p):
        numeric_cols = len(p["measurements"]) + sum(
            1 for f in ("oxygen", "pressure", "flow", "gravity") if p["conditions"].get(f, {}).get("type") == "numeric")
        varied = sum(1 for f in ("oxygen", "pressure", "flow", "gravity", "material")
                     if len(p["conditions"].get(f, {}).get("distinct_values")
                            or p["conditions"].get(f, {}).get("values") or []) > 1)
        model_terms = match_keywords(p["_text"], cfg.MODELING_KEYWORDS)
        score = (0.4 * _saturate(numeric_cols, 5) + 0.3 * _saturate(varied, 3)
                 + 0.2 * _saturate(p["row_count"], 30) + 0.1 * _saturate(len(model_terms), 1))
        why = (f"{numeric_cols} numeric column(s) (40%), {varied} varied test condition(s) (30%), "
               f"{p['row_count']} records (20%), modeling terms found: {', '.join(model_terms) or 'none'} (10%).")
        return score, why, {"numeric_columns": numeric_cols, "varied_conditions": varied, "modeling_terms": model_terms}
