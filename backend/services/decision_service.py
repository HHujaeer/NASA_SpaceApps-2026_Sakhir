"""Transparent question-specific relevance ranking, not a hazard severity estimate."""
import re
from services.ranking_service import RankingService
from services.csv_service import match_keywords


def mode_for(question):
    low = question.lower()
    if re.search(r'\b(rank\w*|recommend\w*|most useful|most relevant|most critical|prioriti\w*|best|which.*(?:use|help))\b', low):
        return 'ranking'
    if re.search(r'\b(compar\w*|versus|vs\.?|differences?|similarities)\b', low):
        return 'comparison'
    if re.search(r'\b(predict\w*|forecast\w*|future|what if|would happen|will happen)\b', low):
        return 'scenario'
    if re.search(r'\b(summar\w*|overview|main findings)\b', low):
        return 'summary'
    return 'question'


def ranking_for(config, csv, question, terms, ids):
    low = question.lower()
    choices = [('lunar_habitat', r'lunar|moon'), ('mars_habitat', r'mars|martian'),
               ('pressurized_rover', r'rover'), ('fire_detection', r'detect|smoke|sensor'),
               ('fire_suppression', r'suppress|extinguish|quench'),
               ('predictive_modeling', r'predict|model|simulat'), ('fire_prevention', r'material|flammab|prevent')]
    category = next((key for key, pattern in choices if re.search(pattern, low)), 'iss_spacecraft')
    base = RankingService(config, csv).rank(category)
    ranked = []
    for candidate in base['ranked']:
        if candidate['id'] not in ids:
            continue
        profile = csv.build_profile(candidate['id'])
        hits = match_keywords(profile['_text'], terms)
        coverage = len(hits) / max(1, len(terms))
        ranked.append(dict(investigation_id=candidate['id'], name=profile['name'],
                           score=round(0.65*candidate['score']+35*coverage, 1),
                           category_score=candidate['score'], matched_terms=hits,
                           record_count=profile['row_count'], completeness=profile['data_quality']['completeness']))
    ranked.sort(key=lambda p: (-p['score'], p['investigation_id']))
    for n, entry in enumerate(ranked, 1):
        entry['rank'] = n
    return dict(category=category, category_label=base['category_label'], ranked=ranked,
                methodology='65% configurable category relevance + 35% coverage of query terms in investigation metadata/table text. Scores are heuristic relevance, not physical risk or predictive confidence.',
                disclaimer='Application-generated ordering of the loaded evidence only; not a NASA ranking, validated safety priority, or estimate of mission risk.')


DECISION_TASK = """Help the user explore and choose among the investigations using only supplied evidence.
For rankings, explain the provided application scores and give a cited, question-specific reason and important limitation for each investigation. Rank usefulness for the stated purpose, never claim these scores measure danger or criticality. If relevance and physical risk differ, explain that distinction.
For comparisons, compare objectives, fuel/material, experimental conditions, available outcomes, source quality and missing data. Do not compare incompatible units or assume identical test conditions. Never fill missing cells from another source without identifying that source and any conflict.
For summaries, provide a short cited summary for each requested investigation: purpose, observed findings, and limits.
For recommendations, separate supported evidence from AI interpretation; explain how each recommendation follows from cited observations and what additional validation is needed.
For future questions, use a heading 'Scenario interpretation (not a validated forecast)'. State assumptions, qualitative implications supported by evidence, and what new measurements/model validation would be required. Do not invent numerical predictions, probabilities, hazard scores or mission-specific performance. If no suitable evidence exists, state that a forecast cannot be made. A request about the future can accompany a ranking or comparison.
Use readable markdown with tables when comparing investigations. Cite factual statements with the supplied tags. Historical chat is for resolving references only, never a source of scientific evidence.
"""
