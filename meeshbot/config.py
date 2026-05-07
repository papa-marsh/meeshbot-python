import os
from zoneinfo import ZoneInfo

GROUPME_TOKEN = os.environ.get("GROUPME_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
BALLDONTLIE_API_KEY = os.environ.get("BALLDONTLIE_API_KEY", "")

GROUPME_WEBHOOK_TOKEN = os.environ.get("GROUPME_WEBHOOK_TOKEN", "")
TESTING_GROUP_ID = os.environ.get("TESTING_GROUP_ID", "")

DATABASE_URL = os.environ.get("DATABASE_URL", "")
AI_DATABASE_URL = os.environ.get("AI_DATABASE_URL", "")

TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "America/New_York"))
