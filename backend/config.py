"""Configuration for the Space Fire Intelligence backend.

Everything tunable lives here or in environment variables (see .env.example).
Nothing in this file is an experimental finding. The reference environments and
keyword lists below are *application settings* used for scoring and retrieval;
edit them freely.

Keyword syntax used by the ranking / retrieval code:
  "smoke"      whole word (plural "smokes" also matches)
  "suppress*"  prefix match (suppress, suppression, suppressant, ...)
  "space station"  multi-word phrase
"""
import json
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:  # optional: load backend/.env if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover
    pass

# --------------------------------------------------------------------------- #
# AI providers. Anything that speaks the OpenAI "chat/completions" protocol can
# be added here (or use AI_PROVIDER=custom with AI_BASE_URL).
# --------------------------------------------------------------------------- #
PROVIDERS = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "max_tokens_param": "max_completion_tokens",
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "key_env": "XAI_API_KEY",
        "max_tokens_param": "max_tokens",
    },
    "custom": {
        "base_url": "",  # supply AI_BASE_URL
        "key_env": "AI_API_KEY",
        "max_tokens_param": "max_tokens",
    },
}

# --------------------------------------------------------------------------- #
# Ranking
# --------------------------------------------------------------------------- #
DEFAULT_WEIGHTS = {
    "mission_relevance": 30,
    "fire_safety_relevance": 25,
    "data_quality": 20,
    "environmental_similarity": 15,
    "predictive_modeling_value": 10,
}

RANKING_DISCLAIMER = (
    "These are application-generated relevance scores computed from the CSV "
    "contents with the configurable criteria shown. They are not NASA-approved "
    "rankings and do not represent NASA's assessment of any investigation."
)

# Reference habitat atmospheres used ONLY for the 'environmental similarity'
# criterion. These are ASSUMPTIONS you should review/replace with the values your
# program uses. They are not experimental results.
ENV_PROFILES = {
    "iss": {"label": "ISS cabin (assumed)", "pressure_kpa": 101.3, "oxygen_pct": 21.0, "gravity_g": 0.0},
    "lunar_habitat": {"label": "Lunar habitat (assumed)", "pressure_kpa": 70.3, "oxygen_pct": 26.5, "gravity_g": 0.166},
    "mars_habitat": {"label": "Mars habitat (assumed)", "pressure_kpa": 70.3, "oxygen_pct": 26.5, "gravity_g": 0.38},
}
# Distance at which similarity for a parameter drops to 0.
ENV_TOLERANCE = {"pressure_kpa": 30.0, "oxygen_pct": 10.0, "gravity_g": 0.5}

FIRE_KEYWORDS = [
    "fire", "flame", "flammab*", "ignit*", "combust*", "burn*", "smolder*",
    "flame spread", "extinguish*", "suppress*", "smoke", "pyrolysis",
]
MODELING_KEYWORDS = ["model*", "simulat*", "predict*", "correlat*", "numerical", "regression", "validat*", "cfd"]

# Per-category keywords. mission_keywords -> 'mission relevance'; safety_keywords
# add to 'fire safety relevance' on top of FIRE_KEYWORDS (empty = general only).
SPACEFLIGHT_KEYWORDS = ["iss", "space station", "spacecraft", "microgravity", "low gravity", "reduced gravity", "orbit*", "crew*"]
CATEGORIES = {
    "iss_spacecraft": {
        "label": "Spacecraft and ISS fire safety",
        "mission_keywords": ["iss", "space station", "spacecraft", "microgravity", "orbit*", "cabin", "low gravity"],
        "safety_keywords": [],
        "env_profiles": ["iss"],
    },
    "lunar_habitat": {
        "label": "Lunar habitats",
        "mission_keywords": ["lunar", "moon", "habitat*", "partial gravity", "reduced gravity", "0.166"],
        "safety_keywords": [],
        "env_profiles": ["lunar_habitat"],
    },
    "mars_habitat": {
        "label": "Mars habitats",
        "mission_keywords": ["mars", "martian", "habitat*", "partial gravity", "reduced gravity", "0.38"],
        "safety_keywords": [],
        "env_profiles": ["mars_habitat"],
    },
    "pressurized_rover": {
        "label": "Pressurized rovers",
        "mission_keywords": ["rover", "vehicle", "pressuri*", "cabin", "lunar", "mars", "martian"],
        "safety_keywords": [],
        "env_profiles": ["lunar_habitat", "mars_habitat"],
    },
    "fire_prevention": {
        "label": "Fire prevention",
        "mission_keywords": SPACEFLIGHT_KEYWORDS + ["lunar", "mars", "habitat*"],
        "safety_keywords": ["flammab*", "ignit*", "material*", "limiting oxygen", "oxygen index", "fire resistan*", "flame resistan*", "prevent*"],
        "env_profiles": ["iss", "lunar_habitat", "mars_habitat"],
    },
    "fire_detection": {
        "label": "Fire detection",
        "mission_keywords": SPACEFLIGHT_KEYWORDS + ["lunar", "mars", "habitat*"],
        "safety_keywords": ["smoke", "detect*", "particulate*", "aerosol*", "alarm*", "obscuration", "carbon monoxide", "sensor*"],
        "env_profiles": ["iss", "lunar_habitat", "mars_habitat"],
    },
    "fire_suppression": {
        "label": "Fire suppression",
        "mission_keywords": SPACEFLIGHT_KEYWORDS + ["lunar", "mars", "habitat*"],
        "safety_keywords": ["suppress*", "extinguish*", "water mist", "mist", "inert*", "agent*", "quench*", "co2", "nitrogen"],
        "env_profiles": ["iss", "lunar_habitat", "mars_habitat"],
    },
    "predictive_modeling": {
        "label": "Predictive fire modeling",
        "mission_keywords": SPACEFLIGHT_KEYWORDS + ["lunar", "mars", "habitat*"],
        "safety_keywords": MODELING_KEYWORDS,
        "env_profiles": ["iss", "lunar_habitat", "mars_habitat"],
    },
}

# --------------------------------------------------------------------------- #
# CSV column detection. Column names are normalised (lower-case, non-alphanumerics
# -> "_") and matched as whole tokens, e.g. "O2_pct" matches the alias "o2".
# Add aliases here if your standardized CSVs use other column names.
# --------------------------------------------------------------------------- #
FIELD_ALIASES = {
    "name": ["experiment_name", "experiment", "investigation_name", "investigation", "test_name", "title"],
    "material": ["fuel_type", "fuel", "material", "sample_material", "sample", "specimen"],
    "oxygen": ["o_initial_ambient_composition", "oxygen_concentration", "oxygen_percent", "oxygen_pct", "oxygen_fraction", "oxygen", "o2"],
    "pressure": ["ambient_pressure", "total_pressure", "chamber_pressure", "pressure"],
    "flow": ["airflow", "air_flow", "flow_velocity", "flow_speed", "forced_flow", "ventilation", "velocity", "flow"],
    "gravity": ["gravity_level", "g_level", "gravity", "acceleration"],
    "sensors": ["sensors", "sensor", "instruments", "instrument", "detector", "diagnostics", "diagnostic"],
    "objective": ["objectives", "objective", "purpose", "goal", "aim"],
    "mission": ["mission", "platform", "facility", "application", "relevance"],
    "source": ["source_reference", "source", "references", "reference", "citation", "doi", "url", "publication", "dataset"],
    "findings": ["findings", "finding", "results", "result", "outcome", "conclusion", "observations", "observation"],
    "notes": ["notes", "description", "summary", "comments", "remarks"],
}
# Used to decide which numeric columns are 'measurements' (id-like columns excluded)
ID_LIKE_TOKENS = {"id", "run", "index", "idx", "no", "number", "row", "seq"}

# Text values in a gravity column -> g (only applied when they clearly match)
GRAVITY_TEXT_KEYWORDS = [("micro", 0.0), ("zero", 0.0), ("lunar", 0.166), ("moon", 0.166),
                         ("martian", 0.38), ("mars", 0.38), ("earth", 1.0), ("normal", 1.0)]

# --------------------------------------------------------------------------- #
# Fire safety insight topics
# --------------------------------------------------------------------------- #
INSIGHT_TOPICS = {
    "material_flammability": {"label": "Material flammability", "keywords": ["flammab*", "ignit*", "material*", "fuel*", "burn*", "flame spread", "limiting oxygen"]},
    "oxygen_concentration": {"label": "Oxygen concentration", "keywords": ["oxygen", "o2", "limiting oxygen", "oxygen concentration"]},
    "microgravity_combustion": {"label": "Microgravity combustion", "keywords": ["microgravity", "low gravity", "reduced gravity", "zero gravity", "partial gravity", "buoyan*"]},
    "smoke_detection": {"label": "Smoke detection", "keywords": ["smoke", "detect*", "particulate*", "aerosol*", "alarm*", "obscuration"]},
    "fire_suppression": {"label": "Fire suppression", "keywords": ["suppress*", "extinguish*", "mist", "inert*", "agent*", "quench*"]},
    "future_habitats": {"label": "Future lunar and Martian habitats", "keywords": ["lunar", "moon", "mars", "martian", "habitat*", "partial gravity", "exploration"]},
}


def _split_csv(value):
    return [v.strip() for v in (value or "").split(",") if v.strip()]


class Config:
    """Reads settings from the environment. Pass overrides (e.g. in tests)."""

    def __init__(self, env=None, **overrides):
        env = os.environ if env is None else env
        self.DATA_DIR = Path(env.get("DATA_DIR") or BASE_DIR / "data" / "experiments")
        self.RAG_INDEX_PATH = Path(env.get("RAG_INDEX_PATH") or BASE_DIR / "data" / "rag" / "index.sqlite")
        self.EMBEDDING_MODEL = env.get("EMBEDDING_MODEL") or "text-embedding-3-small"
        self.CORS_ORIGINS = _split_csv(env.get("CORS_ORIGINS", "*")) or ["*"]
        self.MAX_UPLOAD_BYTES = int(env.get("MAX_UPLOAD_BYTES") or 5 * 1024 * 1024)

        # AI (model is intentionally not defaulted: set AI_MODEL)
        self.AI_PROVIDER = (env.get("AI_PROVIDER") or "").strip().lower()
        self.AI_MODEL = (env.get("AI_MODEL") or "").strip()
        self.AI_BASE_URL = (env.get("AI_BASE_URL") or "").strip()
        self.AI_API_KEY = (env.get("AI_API_KEY") or "").strip()
        self.AI_REASONING_EFFORT = (env.get("AI_REASONING_EFFORT") or "").strip()
        self.EMBEDDING_TIMEOUT_SECONDS = float(env.get("EMBEDDING_TIMEOUT_SECONDS") or 5)
        self.MAX_CHUNKS_PER_INVESTIGATION = int(env.get("MAX_CHUNKS_PER_INVESTIGATION") or 3)
        self.AI_TIMEOUT_SECONDS = float(env.get("AI_TIMEOUT_SECONDS") or 60)
        temp = (env.get("AI_TEMPERATURE") or "").strip()
        self.AI_TEMPERATURE = float(temp) if temp else None
        max_tokens = (env.get("AI_MAX_TOKENS") or "").strip()
        self.AI_MAX_TOKENS = int(max_tokens) if max_tokens else None
        self._env = env

        # Retrieval limits
        self.MAX_CONTEXT_CHARS = int(env.get("MAX_CONTEXT_CHARS") or 12000)
        self.MAX_INVESTIGATIONS_PER_QUERY = int(env.get("MAX_INVESTIGATIONS_PER_QUERY") or 3)
        self.MAX_ROWS_PER_INVESTIGATION = int(env.get("MAX_ROWS_PER_INVESTIGATION") or 15)

        # Ranking weights (percent). Override with RANKING_WEIGHTS='{"data_quality": 30, ...}'
        self.RANKING_WEIGHTS = dict(DEFAULT_WEIGHTS)
        raw = (env.get("RANKING_WEIGHTS") or "").strip()
        if raw:
            self.RANKING_WEIGHTS.update(json.loads(raw))

        for key, value in overrides.items():
            setattr(self, key, value)

    def ai_settings(self):
        """Resolved provider settings, or None if the provider is unknown."""
        provider = PROVIDERS.get(self.AI_PROVIDER)
        if provider is None:
            return None
        key = self.AI_API_KEY or self._env.get(provider["key_env"], "").strip()
        return {
            "provider": self.AI_PROVIDER,
            "base_url": (self.AI_BASE_URL or provider["base_url"]).rstrip("/"),
            "api_key": key,
            "max_tokens_param": provider["max_tokens_param"],
        }
