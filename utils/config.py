"""Environment loading and shared constants."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


SEARCH_ENDPOINT     = os.environ["AZURE_SEARCH_ENDPOINT"]
SEARCH_KEY          = os.environ["AZURE_SEARCH_API_KEY"]
SEARCH_INDEX        = os.environ["AZURE_SEARCH_INDEX"]
SEMANTIC_CONFIG     = os.environ.get("AZURE_SEARCH_SEMANTIC_CONFIG", "default-semantic")
SEARCH_API_VERSION  = os.environ.get("AZURE_SEARCH_API_VERSION", "2025-11-01-preview")

AOAI_ENDPOINT   = os.environ["AZURE_OPENAI_ENDPOINT"]
AOAI_KEY        = os.environ["AZURE_OPENAI_API_KEY"]
AOAI_DEPLOYMENT = os.environ["AZURE_OPENAI_CHAT_DEPLOYMENT"]
AOAI_VERSION    = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")

PROMPTS_DIR = ROOT / "prompts"
