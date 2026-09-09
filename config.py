"""
config.py
---------
All settings live here so you (or your supervisor) can tune thresholds
without touching the actual logic in the other files.
"""

import os

# =========================================================
# API KEYS / VISION MODEL ACCESS
# Set these as environment variables before running the program.
# NEVER type real keys/credentials directly into this file if it
# will be committed to git / shared - use environment variables.
# =========================================================

# Which way to reach Claude for the vision checks: "anthropic" (direct
# API key) or "bedrock" (AWS). Ask your supervisor which one Truuth uses.
VISION_LLM_PROVIDER = os.environ.get("VISION_LLM_PROVIDER", "anthropic")

# --- Option A: direct Anthropic API key ---
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# --- Option B: AWS Bedrock ---
# AWS now supports TWO ways to authenticate with Bedrock:
#
#   B1. Bedrock API key (simplest) - a single long-term key starting
#       with "ABSK...". Set BEDROCK_API_KEY and nothing else AWS-related
#       is needed.
#
#   B2. Traditional AWS Access Key ID + Secret Access Key pair, picked
#       up automatically by boto3 from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY.
#
# If BEDROCK_API_KEY is set, it takes priority over the access key pair.
BEDROCK_API_KEY = os.environ.get("BEDROCK_API_KEY", "")

AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-2")  # Sydney region
BEDROCK_MODEL_ID = os.environ.get(
    "BEDROCK_MODEL_ID", "anthropic.claude-sonnet-4-6-v1:0"
)  # confirm the exact model ID enabled in Truuth's Bedrock console - it varies by account/region

# Optional - only needed if you want Tier 2 (Street View) enabled.
# Leave blank to skip Tier 2 automatically.
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")

# =========================================================
# THRESHOLDS
# =========================================================

# EXIF GPS distance beyond which it's considered a mismatch (metres)
EXIF_GPS_DISTANCE_THRESHOLD_M = 300

# EXIF timestamp difference beyond which it's considered a mismatch (minutes)
EXIF_TIME_DIFF_THRESHOLD_MIN = 60

# Reverse geocoding: how far (metres) the claimed point can be from the
# nearest known road/address before Tier 3 is marked FAIL
TIER3_MAX_DISTANCE_TO_ROAD_M = 150

# Weather categories considered a "MAJOR" mismatch when paired together
# (order doesn't matter - checked both ways)
MAJOR_WEATHER_MISMATCH_PAIRS = [
    ("snow", "clear"),
    ("snow", "sunny"),
    ("storm", "clear"),
    ("storm", "calm"),
    ("rain", "clear"),   # heavy rain vs clear is treated as MAJOR; light vs clear is MINOR (handled in code)
    ("fog", "clear"),
]

# =========================================================
# VISION LLM SETTINGS
# =========================================================
CLAUDE_MODEL = "claude-sonnet-4-6"  # vision-capable model used for photo analysis
VISION_SELF_CONSISTENCY_RUNS = 1     # set to 3 for majority-vote checking (uses more API calls)

# =========================================================
# NETWORK / API ENDPOINTS (all free, no key required)
# =========================================================
NOMINATIM_BASE = "https://nominatim.openstreetmap.org"
OVERPASS_BASE = "https://overpass-api.de/api/interpreter"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

# Nominatim/Overpass usage policy requires a descriptive User-Agent
USER_AGENT = "TruuthClaimVerifier/1.0 (student internship project)"
