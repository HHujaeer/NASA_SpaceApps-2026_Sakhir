"""Retrieval + grounded AI features: research assistant, summaries, fire safety insights.

Flow: retrieve saved report/metadata passages and CSV rows -> build a bounded
evidence context -> ask the AI (which may use nothing else) -> return the answer with
backend-built references. If nothing relevant is found the AI is NOT called.
"""
from __future__ import annotations

from pathlib import Path
from time import perf_counter
import json
import math
import re
from functools import lru_cache

import config as cfg
from services.ai_service import AIServiceError
from services.csv_service import DataError, InvalidRequest, match_keywords

STOPWORDS = {
    "the", "and", "for", "are", "was", "were", "what", "which", "when", "where", "how", "why", "who", "does",
    "did", "can", "could", "would", "should", "with", "from", "that", "this", "these", "those", "there", "their",
    "about", "into", "than", "then", "have", "has", "had", "been", "being", "any", "all", "show", "tell", "give",
    "please", "data", "experiment", "experiments", "investigation", "investigations", "result", "results",
    "compare", "between", "using", "used", "use", "more", "most", "less", "some", "such", "also", "its", "our",
}

ASK_TASK = ("Answer the question using only the data context. Use the headings 'Experimental results (from the data)', "
            "'AI interpretation' and 'Data gaps' where relevant. If the context cannot answer the question, say so.")
SUMMARY_TASK = ("Summarize this experiment from the data context only, under these headings: Objectives, Conditions, "
                "Variables, Measurements, Findings, then 'AI interpretation: relevance to spacecraft, lunar habitats and "
                "Mars missions'. Write 'Not reported in the data' for anything missing. The relevance section must be "
                "labelled as interpretation and must rely only on conditions present in the data.")
INSIGHT_TASK = ("Produce evidence-based fire safety insights on the topic '{label}' from the data context only. Use exactly "
                "these headings: '## Measured findings' (values and observations in the data, each cited), "
                "'## Interpretations' (your reasoning, clearly not experimental findings), '## Data gaps'. Include "
                "implications for future lunar and Martian habitats only as interpretation and only when the data supports them.")

SECTION_PATTERNS = [("experimental_results", r"experimental results|measured"), ("ai_interpretation", r"interpret"),
                    ("data_gaps", r"gap|limitation|not available")]
_CITE_GROUP = re.compile(r"\[([^\]]+)\]")
_TAG = re.compile(r"^E\d+(?::[RC]\d+)?$")


class ResearchService:
    def __init__(self, config, csv_service, ai_service):
        self.config = config
        self.csv = csv_service
        self.ai = ai_service
        from services.semantic_service import SemanticIndex
        self.semantic = SemanticIndex(config)

    # ------------------------------------------------------------------ #
    # Public features
    # ------------------------------------------------------------------ #
    @staticmethod
    def _history(history):
        if history is None:
            return []
        if not isinstance(history, list) or len(history) > 12 or any(
            not isinstance(m, dict) or m.get("role") not in ("user", "assistant")
            or not isinstance(m.get("content"), str) or len(m["content"]) > 6000 for m in history
        ):
            raise InvalidRequest("history must contain at most 12 user/assistant messages, up to 6000 characters each.")
        return [{"role": m["role"], "content": m["content"][:1500]} for m in history[-6:]]

    def ask(self, question, history=None):
        started = perf_counter()
        from services.decision_service import mode_for, ranking_for, DECISION_TASK
        if not isinstance(question, str) or not 3 <= len(question.strip()) <= 1000:
            raise InvalidRequest("'question' must be a string of 3 to 1000 characters.")
        history = self._history(history)
        previous = " ".join(m["content"] for m in history[-4:] if m["role"] == "user")
        query = question + " " + previous
        words, numbers = self._question_terms(query)
        if not words and not numbers:
            raise InvalidRequest("The question contains no searchable terms.")
        mode = mode_for(question)
        profiles = []
        for inv_id in self.csv.list_investigation_ids():
            try:
                profiles.append(self.csv.build_profile(inv_id))
            except DataError:
                continue
        mentioned = []
        canonical = re.sub(r'[^a-z0-9]+', ' ', query.lower())
        for profile in profiles:
            aliases = [profile["id"], profile["name"]] + profile.get("metadata", {}).get("Comment[Investigation Acronym]", [])
            if any(re.search(r'(?<![a-z0-9])' + re.escape(re.sub(r'[^a-z0-9]+', ' ', alias.lower())) + r'(?![a-z0-9])', canonical) for alias in aliases):
                mentioned.append(profile["id"])
        decision = mode != "question"
        ids = mentioned or ([p["id"] for p in profiles] if decision else None)
        retrieved = self._retrieve(words, numbers, only_ids=ids, include_unmatched=bool(ids), semantic_query=query)
        if not retrieved:
            return self._no_data("No records or source passages matched this question.", question=question)
        ranking = ranking_for(self.config, self.csv, query, words, [e["profile"]["id"] for e in retrieved]) if mode == "ranking" else None
        if ranking:
            facts = {p["investigation_id"]: p for p in ranking["ranked"]}
            for entry in retrieved:
                entry["ranking_facts"] = facts[entry["profile"]["id"]]
        context, truncated = self._build_context(retrieved)
        task = ASK_TASK + "\n" + DECISION_TASK
        if ranking:
            task += "\nRanking methodology: " + ranking["methodology"]
        if history:
            task += "\nPrior conversation (not scientific evidence):\n" + json.dumps(history)
        retrieval_ms = round((perf_counter()-started)*1000, 2)
        result = self._run_ai(task, retrieved, context, truncated, question=question)
        result["timing_ms"]["retrieval"] = retrieval_ms
        result.update(mode=mode, ranking=ranking)
        return result

    def chat(self, inv_id, question, history=None):
        """Investigation-scoped conversation with validated declarative chart requests."""
        from services.chart_service import build_chart
        from services.decision_service import DECISION_TASK
        if not isinstance(question, str) or not 3 <= len(question.strip()) <= 1000:
            raise InvalidRequest("'question' must be a string of 3 to 1000 characters.")
        history = self._history(history)
        profile, df = self.csv.load(inv_id)
        previous = " ".join(m["content"] for m in history[-4:] if m["role"] == "user")
        words, numbers = self._question_terms(question + " " + previous)
        retrieved = self._retrieve(words, numbers, only_ids=[inv_id], semantic_query=question + " " + previous)
        if not retrieved:
            entry = self._entry("E1", profile, df, self._spread(list(df.index), 5), 1, "sample")
            entry["chunks"] = self._select_chunks(self._load_chunks(inv_id), ["conclu*", "objective*"], [])
            retrieved = [entry]
        context, truncated = self._build_context(retrieved)
        task = (ASK_TASK + DECISION_TASK +
                " Return ONLY a JSON object with keys answer (a markdown string with citations) and chart. "
                "chart must be null unless the user requests a visualization. Otherwise chart must be "
                '{"type":"scatter"|"line"|"bar", "x":"exact source column", "y":"exact source column"}. '
                "Select only columns listed in context. Do not generate code, points, or calculated values. "
                "If requested quantities are absent from source columns, explain the gap and set chart null. "
                "The server builds charts from all paired source rows, independently of the sampled evidence. "
                "Prior conversation below is for resolving follow-up requests, not evidence:\n" + json.dumps(history))
        result = self._run_ai(task, retrieved, context, truncated, question=question)
        try:
            raw = result["answer"].strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
            payload = json.loads(raw)
            if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str) or "chart" not in payload:
                raise ValueError("Invalid response schema")
        except (ValueError, TypeError) as exc:
            raise AIServiceError("ai_bad_response", "The assistant returned an invalid response. Please try again.",
                                 details={"references": result["references"]}) from exc
        try:
            result["chart"] = build_chart(payload["chart"], profile, df)
        except InvalidRequest as exc:
            result["chart"] = None
            result["chart_error"] = str(exc)
        result["answer"] = payload["answer"]
        result["sections"] = self.parse_sections(payload["answer"])
        result["citation_check"] = self.check_citations(payload["answer"], {r["tag"] for r in result["references"]})
        return result

    def summarize(self, inv_id):
        if not isinstance(inv_id, str) or not inv_id:
            raise InvalidRequest("'investigation_id' is required.")
        profile, df = self.csv.load(inv_id)
        retrieved = [self._entry("E1", profile, df, row_numbers=self._spread(list(df.index), 25), score=1, selection="all"
                                 if len(df) <= 25 else "sample")]
        retrieved[0]["chunks"] = self._select_chunks(
            self._load_chunks(inv_id), ["conclu*", "finding*", "result*", "objective*"], [])
        context, truncated = self._build_context(retrieved)
        result = self._run_ai(SUMMARY_TASK, retrieved, context, truncated)
        result.update({"investigation_id": inv_id, "name": profile["name"], "facts": self.csv.public(profile)})
        return result

    def insights(self, topic, investigation_ids=None):
        topics = cfg.INSIGHT_TOPICS
        if topic not in topics:
            raise InvalidRequest(f"Unknown topic '{topic}'. Valid: {sorted(topics)}")
        if investigation_ids is not None and not (isinstance(investigation_ids, list)
                                                  and all(isinstance(i, str) for i in investigation_ids)):
            raise InvalidRequest("'investigation_ids' must be a list of strings.")
        retrieved = self._retrieve(topics[topic]["keywords"], [], only_ids=investigation_ids)
        if not retrieved:
            return self._no_data(f"No records or source passages matched the topic '{topics[topic]['label']}'.",
                                 topic=topic)
        context, truncated = self._build_context(retrieved)
        result = self._run_ai(INSIGHT_TASK.format(label=topics[topic]["label"]), retrieved, context, truncated)
        result.update({"topic": topic, "topic_label": topics[topic]["label"]})
        return result

    def topics(self):
        return [{"key": k, "label": v["label"]} for k, v in cfg.INSIGHT_TOPICS.items()]

    # ------------------------------------------------------------------ #
    # Retrieval
    # ------------------------------------------------------------------ #
    @staticmethod
    def _question_terms(question):
        low = question.lower()
        numbers = list(dict.fromkeys(re.findall(r"\d+(?:\.\d+)?", low)))
        words = []
        for w in re.findall(r"[a-z][a-z0-9]*", low):
            if w in STOPWORDS or (len(w) < 3 and w not in ("o2", "co")):
                continue
            stem = w[:-1] if w.endswith("s") and len(w) > 4 else w
            words.append(stem + "*" if len(stem) >= 4 else stem)
        if re.search(r"\b(findings?|results?|conclu\w*|summary|summarize)\b", low):
            words.extend(["conclu*", "finding*", "result*"])
        return list(dict.fromkeys(words)), numbers

    def _retrieve(self, word_kws, number_kws, only_ids=None, include_unmatched=False, semantic_query=None):
        """Score every CSV (read on demand) and return the most relevant ones."""
        max_inv = self.config.MAX_INVESTIGATIONS_PER_QUERY
        max_rows = self.config.MAX_ROWS_PER_INVESTIGATION
        semantic_scores = self.semantic.search(semantic_query or " ".join(word_kws).replace("*", ""))
        candidates = []
        ids = self.csv.list_investigation_ids()
        if only_ids is not None:
            unknown = [i for i in only_ids if i not in ids]
            if unknown:
                raise InvalidRequest(f"Unknown investigation id(s): {unknown}")
            ids = only_ids
        for inv_id in ids:
            try:
                profile, df = self.csv.load(inv_id)
            except DataError:
                continue
            inv_hits = match_keywords(profile["_text"], word_kws)
            chunks = self._select_chunks(self._load_chunks(inv_id), word_kws, number_kws, semantic_scores, limit=self.config.MAX_CHUNKS_PER_INVESTIGATION)
            if include_unmatched and not chunks:
                chunks = self._select_chunks(self._load_chunks(inv_id), ["conclu*", "objective*"], [])
            row_scores = {}
            for values in df.itertuples(index=True, name=None):
                rn = values[0]
                row_text = " ".join(str(v) for v in values[1:] if v is not None).lower()
                hits = len(match_keywords(row_text, word_kws + number_kws))
                if hits:
                    row_scores[rn] = hits
            if not inv_hits and not row_scores and not chunks and not include_unmatched:
                continue
            score = len(inv_hits) * 2 + max(row_scores.values(), default=0) + sum(c["_score"] for c in chunks)
            candidates.append((score, profile, df, row_scores, chunks))
        candidates.sort(key=lambda c: (-c[0], c[1]["id"]))

        retrieved = []
        for n, (score, profile, df, row_scores, chunks) in enumerate(candidates[:max_inv], 1):
            if row_scores:
                best = sorted(row_scores, key=lambda r: (-row_scores[r], r))[:max_rows]
                rows, selection = sorted(best), "matched"
            else:
                rows, selection = self._spread(list(df.index), min(5, max_rows)), "sample"
            entry = self._entry(f"E{n}", profile, df, rows, score, selection)
            entry["chunks"] = chunks
            entry["retrieval_method"] = "hybrid" if semantic_scores else "keyword"
            retrieved.append(entry)
        return retrieved

    def _load_chunks(self, inv_id):
        path = self.csv._path(inv_id).with_suffix(".chunks.json")
        if not path.exists():
            return []
        return self._read_chunks(str(path), path.stat().st_mtime_ns, path.stat().st_size, inv_id)

    @staticmethod
    @lru_cache(maxsize=32)
    def _read_chunks(filename, modified, size, inv_id):
        try:
            chunks = json.loads(Path(filename).read_text(encoding="utf-8"))
            if not isinstance(chunks, list) or any(
                not isinstance(c, dict) or not all(k in c for k in ("id", "text", "file", "kind"))
                or c.get("investigation_id") != inv_id for c in chunks
            ):
                raise ValueError("Invalid chunk schema")
            return chunks
        except (OSError, ValueError) as exc:
            raise DataError(f"Cannot read saved chunks for {inv_id}: {exc}") from exc

    @staticmethod
    def _select_chunks(chunks, words, numbers, semantic_scores=None, limit=6):
        """Length-normalized lexical ranking with rare-term weighting and overlap removal.

        Search report passages directly, independently of CSV/profile vocabulary.
        Record chunks duplicate CSV rows, so keep them in the row retrieval path.
        """
        semantic_scores = semantic_scores or {}
        chunks = [c for c in chunks if c["kind"] != "record"]
        terms = list(dict.fromkeys(words + numbers))
        frequencies = {term: sum(bool(match_keywords(c["text"], [term])) for c in chunks)
                       for term in terms}
        scored = []
        for chunk in chunks:
            hits = match_keywords(chunk["text"], terms)
            if not hits and chunk["id"] not in semantic_scores:
                continue
            score = sum(math.log(1 + (len(chunks) + 1) / (frequencies[t] + 1)) for t in hits)
            score /= 0.5 + 0.5 * max(len(chunk["text"].split()), 100) / 200
            # Contents pages list section names but provide no findings.
            if re.search(r"\.{4,}", chunk["text"]):
                score *= 0.05
            if chunk.get("section") in ("Conclusions", "Summary") and "conclu*" in words:
                score *= 8
            score += 4 * semantic_scores.get(chunk["id"], 0)
            scored.append(dict(chunk, _score=score))
        selected = []
        for chunk in sorted(scored, key=lambda c: (-c["_score"], c["id"])):
            if any(chunk["file"] == c["file"] and chunk.get("page") == c.get("page")
                   and chunk.get("offset") is not None and c.get("offset") is not None
                   and abs(chunk["offset"] - c["offset"]) < 1800 for c in selected):
                continue
            selected.append(chunk)
            if len(selected) >= limit:
                break
        return selected

    @staticmethod
    def _spread(items, n):
        if len(items) <= n:
            return list(items)
        step = (len(items) - 1) / (n - 1) if n > 1 else 0
        return sorted({items[round(i * step)] for i in range(n)})

    def _entry(self, tag, profile, df, row_numbers, score, selection):
        return {"tag": tag, "profile": profile, "score": score, "row_selection": selection,
                "records": [self.csv.record(df, rn, profile) for rn in row_numbers]}

    # ------------------------------------------------------------------ #
    # Context + references
    # ------------------------------------------------------------------ #
    def _build_context(self, retrieved):
        limit = self.config.MAX_CONTEXT_CHARS
        lines, truncated = [], False
        for index, e in enumerate(retrieved):
            # Reserve a fair share for each investigation in comparisons.
            used = sum(len(x) + 1 for x in lines)
            entry_limit = used + (limit - used) // (len(retrieved) - index)
            p, tag = e["profile"], e["tag"]
            head = [f"[{tag}] Experiment: {p['name']} | file: {p['file']} | id: {p['id']}",
                    f"Rows in file: {p['row_count']}. Columns: {', '.join(p['columns'])}"]
            for key in ("Comment[Objective]", "Comment[Flight Platform]"):
                values = p.get("metadata", {}).get(key)
                if values:
                    head.append(f"Metadata (purpose/procedure, not measured findings), {key}: " + "; ".join(values)[:450])
            if p.get("data_notes"):
                head.append("Source discrepancies and limitations: " + "; ".join(p["data_notes"])[:650])
            if e.get("ranking_facts"):
                head.append("Application relevance ranking (not a scientific measurement): " + json.dumps(e["ranking_facts"]))
            for field, cond in p["conditions"].items():
                if cond.get("type") == "numeric":
                    head.append(f"Range of {field} ({cond['column']}): {cond['min']:g} to {cond['max']:g}"
                                + (f" {cond['unit']}" if cond.get("unit") else " (unit not stated)"))
            for col, st in p["measurements"].items():
                if st:
                    head.append(f"Aggregate over all rows, {col}: n={st['count']}, min={st['min']:g}, max={st['max']:g}, mean={st['mean']:.6g}")
            head.append(f"Records shown ({e['row_selection']}); blank/omitted fields are not reported:")
            header = "\n".join(head)
            remaining = entry_limit - sum(len(x) + 1 for x in lines)
            if len(header) + 1 > remaining:
                truncated = True
                e["records"] = []
                e["chunks"] = []
                continue
            e["context_included"] = True
            lines.extend(head)
            included_chunks = []
            for n, chunk in enumerate(e.get("chunks", []), 1):
                line = f"[{tag}:C{n}] source_type={chunk['kind']} | role={chunk.get('evidence_role', chunk['kind'])} | location={chunk.get('figure', chunk.get('paragraph', 'n/a'))} | {chunk['file']} | page={chunk.get('page', 'n/a')} | row={chunk.get('row_number', 'n/a')} | {chunk['text']}"
                if sum(len(x) + 1 for x in lines) + len(line) + 1 > entry_limit:
                    truncated = True
                    break
                lines.append(line)
                included_chunks.append(chunk)
            e["chunks"] = included_chunks
            included_records = []
            for rec in e["records"]:
                text = "; ".join(f"{c}={str(v)[:300]}" for c, v in rec["values"].items() if v is not None)
                line = f"[{tag}:R{rec['row_number']}] {text}"
                if sum(len(x) + 1 for x in lines) + len(line) + 1 > entry_limit:
                    truncated = True
                    break
                lines.append(line)
                included_records.append(rec)
            e["records"] = included_records
        return "\n".join(lines), truncated

    @staticmethod
    def _references(retrieved):
        refs = []
        for e in retrieved:
            if not e.get("context_included"):
                continue
            p = e["profile"]
            refs.append({"tag": e["tag"], "type": "experiment", "investigation_id": p["id"], "name": p["name"],
                         "file": p["file"], "source_references": p["source_references"]["values"]})
            for n, chunk in enumerate(e.get("chunks", []), 1):
                refs.append({"tag": f"{e['tag']}:C{n}", "type": "chunk",
                             "investigation_id": p["id"], "name": p["name"],
                             **{k: v for k, v in chunk.items() if k != "text" and not k.startswith("_")}})
            for rec in e["records"]:
                refs.append({"tag": f"{e['tag']}:R{rec['row_number']}", "type": "record", "investigation_id": p["id"],
                             "name": p["name"], "file": p["file"], "row_number": rec["row_number"],
                             "source_reference": rec["source"]["source_reference"]})
        return refs

    @staticmethod
    def _summary_of(retrieved):
        return [{"tag": e["tag"], "investigation_id": e["profile"]["id"], "name": e["profile"]["name"],
                 "relevance_score": e["score"], "method": e.get("retrieval_method", "keyword"), "row_selection": e["row_selection"],
                 "records_used": [r["row_number"] for r in e["records"]],
                 "chunks_used": [c["id"] for c in e.get("chunks", [])]} for e in retrieved if e.get("context_included")]

    # ------------------------------------------------------------------ #
    # AI call + response shaping
    # ------------------------------------------------------------------ #
    def _run_ai(self, task, retrieved, context, truncated, question=None):
        refs = self._references(retrieved)
        retrieval = self._summary_of(retrieved)
        generation_started = perf_counter()
        try:
            res = self.ai.generate(task, context, question=question)
        except AIServiceError as exc:
            # Keep the retrieved evidence available to the caller even though the AI failed
            exc.details = {"retrieval": retrieval, "references": refs}
            raise
        return {
            "answerable": True,
            "timing_ms": {"generation": round((perf_counter()-generation_started)*1000, 2)},
            "answer": res["text"],
            "sections": self.parse_sections(res["text"]),
            "retrieval": retrieval,
            "context_truncated": truncated,
            "references": refs,
            "citation_check": self.check_citations(res["text"], {r["tag"] for r in refs}),
            "ai": {"provider": res["provider"], "model": res["model"]},
            "disclaimer": ("The answer is AI-generated from the retrieved investigation records and source chunks. Experimental results "
                           "and AI interpretation are separated by headings; verify against the references."),
        }

    @staticmethod
    def _no_data(message, **extra):
        return {"answerable": False, "answer": None, "message": message, "retrieval": [], "references": [],
                "ai": None, **extra}

    @staticmethod
    def parse_sections(text):
        """Split an answer on its markdown/bold headings; None if no known headings."""
        sections, current, buf = {}, None, []
        for line in text.splitlines():
            m = re.match(r"^\s*(?:#{1,6}\s*|\*\*)\s*(.+?)\s*(?:\*\*)?:?\s*$", line)
            title = m.group(1).lower() if m else None
            key = next((k for k, pat in SECTION_PATTERNS if title and re.search(pat, title)), None) if m else None
            if key:
                if current:
                    sections[current] = "\n".join(buf).strip()
                current, buf = key, []
            elif current:
                buf.append(line)
        if current:
            sections[current] = "\n".join(buf).strip()
        return sections or None

    @staticmethod
    def check_citations(text, valid_tags):
        cited = set()
        for group in _CITE_GROUP.findall(text):
            for token in re.split(r"[,;\s]+", group):
                if _TAG.match(token):
                    cited.add(token)
        unknown = sorted(cited - valid_tags)
        return {"cited": sorted(cited), "unknown_citations": unknown, "has_citations": bool(cited),
                "all_citations_valid": bool(cited) and not unknown}
