import os
from dotenv import load_dotenv

load_dotenv()

# Branding
APP_NAME = "LOOP"
APP_TAGLINE = "Local Opportunities and Outdoor Play"

# Database
POSTGRES_USER = os.getenv("POSTGRES_USER", "loop_user")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "loop_pass")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "loop_db")
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

# Master tags - single source of truth for AI prompts and UI filtering
MASTER_TAGS = ["Education", "Outdoors", "STEM", "Arts", "Active", "Social", "Music", "Crafts"]

# Age group tags used by the AI tagger alongside master tags
AGE_TAGS = ["Baby (0-2)", "Preschool (3-5)", "Kids (6-12)", "Teens (13-17)", "All Ages"]

# Geocoding
DEFAULT_ZIP = "02852"
GEOCODER_USER_AGENT = "loop_geocoder"
