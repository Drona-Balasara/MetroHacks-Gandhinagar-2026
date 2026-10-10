"""HeadwayIQ — event-aware metro headway recommendations.

Phase 1 data foundation (see docs/PHASE2_HANDOFF.md):
    from headwayiq.db import connect, init_schema, load_all, load_fixture_rows
    from headwayiq.schema import SCHEMAS, PROVENANCE
    from headwayiq.validation import validate_dataset

Recommendation engine:
    from headwayiq.engine import generate            # context dict -> payload
    from headwayiq import scenarios                   # scenarios.run("stadium_evening")
    from headwayiq.config import Config, DEFAULT      # tunable parameters
"""
from .schema import SCHEMAS, PROVENANCE, FIXTURES
from .validation import validate_dataset, check_referential, ValidationReport
from .engine import generate, recommend_band, analyse_band
from .config import Config, DEFAULT

__all__ = [
    "SCHEMAS", "PROVENANCE", "FIXTURES",
    "validate_dataset", "check_referential", "ValidationReport",
    "generate", "recommend_band", "analyse_band", "Config", "DEFAULT",
]
