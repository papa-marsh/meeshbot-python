"""Create the read-only meeshbot_ai Postgres user used by the AI query_database tool.

The password is sourced from AI_DATABASE_URL at migration time.
Statements are idempotent — safe to run on a DB where the user already exists.
"""

import os
from urllib.parse import urlparse

depends_on = "0006_drop_favorited_by_from_groupmemessage"

AI_DB_USER = "meeshbot_ai"


def upgrade(ctx):
    """Apply migration."""
    ai_database_url = os.environ.get("AI_DATABASE_URL", "")
    if not ai_database_url:
        raise RuntimeError(
            "AI_DATABASE_URL is not set. Cannot create the read-only AI database user."
        )

    password = urlparse(ai_database_url).password
    if not password:
        raise RuntimeError(
            "Could not extract password from AI_DATABASE_URL. "
            "Expected format: postgresql://user:password@host/db"
        )

    ctx.execute(f"""
        DO $$
        BEGIN
            CREATE USER {AI_DB_USER} WITH PASSWORD '{password}';
        EXCEPTION WHEN duplicate_object THEN
            ALTER USER {AI_DB_USER} WITH PASSWORD '{password}';
        END
        $$
    """)
    ctx.execute(f"GRANT CONNECT ON DATABASE meeshbot TO {AI_DB_USER}")
    ctx.execute(f"GRANT USAGE ON SCHEMA public TO {AI_DB_USER}")
    ctx.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {AI_DB_USER}")
    ctx.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {AI_DB_USER}"
    )


def downgrade(ctx):
    """Revert migration."""
    ctx.execute(
        f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM {AI_DB_USER}"
    )
    ctx.execute(f"REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM {AI_DB_USER}")
    ctx.execute(f"REVOKE USAGE ON SCHEMA public FROM {AI_DB_USER}")
    ctx.execute(f"REVOKE CONNECT ON DATABASE meeshbot FROM {AI_DB_USER}")
    ctx.execute(f"DROP USER IF EXISTS {AI_DB_USER}")
