"""Re-export: the corpus lives in the app package so the server (sample
project seeding) and the eval/test suite share one source."""

from app.sample_corpus import *  # noqa: F401,F403
from app.sample_corpus import CorpusDoc, build_corpus  # noqa: F401
