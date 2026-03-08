import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()


def _get_secret(key, default=""):
    """Get a secret from environment variables (.env local) or Streamlit secrets (cloud)."""
    val = os.getenv(key)
    if val:
        return val
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        return default


# Branding
APP_NAME = "LOOP"
APP_TAGLINE = "Local Opportunities and Outdoor Play"

# Database
DATABASE_URL = _get_secret("DATABASE_URL")
if not DATABASE_URL:
    POSTGRES_USER = _get_secret("POSTGRES_USER", "loop_user")
    POSTGRES_PASSWORD = _get_secret("POSTGRES_PASSWORD", "loop_pass")
    POSTGRES_HOST = _get_secret("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = _get_secret("POSTGRES_PORT", "5432")
    POSTGRES_DB = _get_secret("POSTGRES_DB", "loop_db")
    DATABASE_URL = f"postgresql://{POSTGRES_USER}:{quote_plus(POSTGRES_PASSWORD)}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Gemini
GEMINI_API_KEY = _get_secret("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"

# Master tags - single source of truth for AI prompts and UI filtering
MASTER_TAGS = ["Education", "Outdoors", "STEM", "Arts", "Active", "Social", "Music", "Crafts"]

# Age group tags used by the AI tagger alongside master tags
AGE_TAGS = ["Baby (0-2)", "Preschool (3-5)", "Kids (6-12)", "Teens (13-17)", "All Ages"]

# Geocoding
DEFAULT_ZIP = "02852"
GEOCODER_USER_AGENT = "loop_geocoder"
