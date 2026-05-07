# meeshbot

GroupMe bot that receives webhook events, persists messages, dispatches slash commands, and generates LLM-driven chat replies via Anthropic Claude. Runs in Docker on a mac mini. Python 3.14, FastAPI, Oxyde ORM, APScheduler, structlog, uv.

## Architecture

A FastAPI endpoint (`POST /groupme-webhook`) receives all inbound GroupMe messages. The handler runs three steps sequentially:

1. **Persist** — every message is synced to Postgres (group, user, and message records created or updated)
2. **Slash command dispatch** — if the message starts with `/`, look up and execute the matching command function
3. **AI response evaluation** — if the message isn't from MeeshBot itself, run a two-stage LLM pipeline to decide whether and how to reply

This chain lives in `meeshbot/handlers/groupme.py`. Each step is independent — a slash command and an AI response can both fire on the same message.

### Data flow

GroupMe is the source of truth for messages. The webhook delivers them; meeshbot persists a local copy to Postgres for history queries (LLM context windows, scoreboards). The bot posts replies back to GroupMe via bot IDs — each GroupMe group has a dedicated bot ID mapped in `meeshbot/integrations/groupme/secrets.py`.

### LLM two-prompt pipeline

Two-prompt pipeline, two different jobs:

1. **Classifier (`should_respond`)** — cheap Haiku call. Scores 0–100 how likely MeeshBot should reply. Only proceeds if the score meets a set threshold.
2. **Responder (`send_ai_response`)** — stronger Sonnet call. Generates the actual reply, with `web_search` and `web_fetch` tools available.

The classifier always runs on eligible messages; the responder only runs when the classifier clears the threshold. This keeps response quality high without paying the heavier model's cost on every message.

Both live in `meeshbot/integrations/anthropic/chat.py`. System prompts are string constants in `context.py` (`SHOULD_RESPOND_CONTEXT` and `SEND_AI_RESPONSE_CONTEXT`). Model choices and tuning values (history window size, threshold) are module constants in `chat.py`.

**Client-side tools and the agentic loop:** The responder has access to client-side tools (currently `query_database`) in addition to Anthropic's server-side tools (`web_search`, `web_fetch`). Server-side tools are handled transparently by Anthropic's infra. Client-side tools require an agentic loop in `AnthropicClient.generate_response`: when Claude returns `stop_reason: "tool_use"`, the method executes the tool, appends a `tool_result` user message, and calls the API again until `stop_reason` is `end_turn`. Tool definitions and executors live in `tools.py`. The `query_database` tool connects via `AI_DATABASE_URL` (a read-only Postgres user) and executes raw SELECT queries.

**Message-history role convention:** GroupMe is n-party chat, but Anthropic's API expects `user`/`assistant` turns. `AnthropicClient.build_message_entry` maps human messages to `role: "user"` and MeeshBot's own messages to `role: "assistant"`, both prefixed with `"Sender Name (timestamp): text"`. This preserves speaker attribution while maintaining the self-vs-other separation the model reasons about.

**Classifier vs participant framing:** The two prompts consume history differently:

- `send_ai_response` passes history as role-tagged messages — the LLM is *participating in* the conversation
- `should_respond` flattens history into a single user-role text block — the LLM is *analyzing* the conversation from outside, classifying evidence

When adding new LLM features, decide which framing fits and pass history accordingly.

**Structured outputs:** For LLM calls needing strict-shape output, use `AsyncAnthropic.messages.parse` with a private Pydantic model as `output_format`. Two examples exist on `AnthropicClient`: `resolve_timestamp` → `_ResolvedTimestamp`, `score_response_likelihood` → `_ResponseLikelihood`. Read the result via `response.parsed_output`. Raise on `None`; don't silently fall through.

### Scheduler

APScheduler runs a per-minute tick (`scheduled/scheduler.py`) that dispatches due reminders. The scheduler starts and stops via `scheduler_lifespan()`, composed into the app lifespan alongside the database connection in `app.py`.

## Codebase

All application code lives in `meeshbot/`.

- **`app.py`** — FastAPI app, lifespan management (DB + scheduler), route definitions
- **`config.py`** — environment variable reads (API keys, database URL, timezone)
- **`handlers/`** — webhook handler that orchestrates persist → command → AI response
- **`commands/`** — one module per slash command. Each exports an async function taking `GroupMeWebhookPayload`. Registered in `commands/registry.py`, re-exported from `commands/__init__.py`.
- **`integrations/groupme/`** — `client.py` (GroupMe API client, posts via bot IDs), `types.py` (Pydantic models for webhook payloads, messages, groups), `queries.py` (DB operations for messages/users/groups), `secrets.py` (bot ID mappings, admin user IDs, public group IDs)
- **`integrations/anthropic/`** — `client.py` (AnthropicClient wrapper, structured outputs, agentic tool-use loop), `chat.py` (two-prompt pipeline orchestration, history building), `context.py` (system prompt constants), `tools.py` (client-side tool definitions and executors)
- **`models/`** — Oxyde ORM models: `GroupMeGroup`, `GroupMeUser`, `GroupMeMessage`, `Reminder`. Each has a corresponding `.pyi` stub auto-generated by Oxyde.
- **`scheduled/`** — `scheduler.py` (APScheduler config, per-minute tick), `reminders.py` (queries for due reminders, dispatches them to GroupMe)
- **`utils/`** — `logging.py` (structlog configuration), `dates.py` (timezone-aware datetime helpers)
- **`migrations/`** — auto-generated by Oxyde. Excluded from linting and type checking.

## Extending

### Adding a command

1. Create `meeshbot/commands/<name>.py` with an async function taking `GroupMeWebhookPayload`:

```python
from meeshbot.integrations.groupme.client import GroupMeClient
from meeshbot.integrations.groupme.types import GroupMeWebhookPayload

async def mycommand(webhook: GroupMeWebhookPayload) -> None:
    await GroupMeClient().post_message(group_id=webhook.group_id, text="response")
```

2. Re-export from `meeshbot/commands/__init__.py`
3. Register in `meeshbot/commands/registry.py` under `COMMAND_REGISTRY`

Two decorators are available in `registry.py`: `admin_only` (gates on `ADMIN_USER_IDS`) and `no_public` (blocks in public groups). They compose: `no_public(admin_only(func))`.

### Adding a model

1. Create `meeshbot/models/<name>.py` with an Oxyde `Model` subclass
2. Export from `meeshbot/models/__init__.py`
3. Register the module path in `oxyde_config.py` under `MODELS`
4. Run `uv run oxyde makemigrations` to generate migration files and `.pyi` stubs

### Adding LLM features

- New system prompts → string constants in `integrations/anthropic/context.py`
- New structured-output calls → method on `AnthropicClient` with a private `_ModelName(BaseModel)` in `client.py`
- New orchestration (history fetching, prompt assembly, output dispatch) → `chat.py`
- New client-side tools → add a tool definition dict and an `async execute_<name>` function in `tools.py`, then add the tool to `AnthropicClient.generate_response` (as a property + entry in the `tools` list). The agentic loop in `generate_response` dispatches by `block.name`, so add a new `elif block.name == "your_tool"` branch there.

### Adding a scheduled job

Add the job function in `scheduled/` and register it with the scheduler in `scheduled/scheduler.py`. The scheduler runs on a per-minute cron tick — see `_tick()` for the current pattern.

## Operations

### Dependencies

Uses **uv**. Do not use `pip` directly.

```bash
uv add <package>            # add runtime dep
uv add --dev <package>      # add to [dependency-groups.dev]
uv sync                     # install all deps
uv run <command>            # run in venv
```

### Running / deploying

Runs in Docker Compose (FastAPI + Postgres). The `meeshbot/` directory is volume-mounted, so code changes hot-reload without a rebuild.

```bash
just deploy                 # docker down → build → up → migrate → tail logs
just logs                   # tail logs
just shell                  # IPython shell inside the running container
just pull-deploy            # git pull + just deploy (used on mac mini)
```

`just deploy` runs `uv run oxyde migrate` inside the container after startup — migrations are applied automatically on every deploy.

### Linting & types

```bash
uv run ruff check meeshbot     # lint
uv run ruff format meeshbot    # format
uv run mypy meeshbot           # type check
```

Ruff and mypy both exclude `meeshbot/migrations/` and model `.pyi` stubs. Strict mypy — all functions must be fully typed.

### Oxyde ORM

Django-style async ORM with a Rust core ([docs](https://github.com/mr-fatalyst/oxyde)). Config is in `oxyde_config.py` at the repo root. Use existing model definitions and query patterns as reference when adding or extending DB operations.

Oxyde is in alpha. The fork at `~/Repositories/oxyde` can be used for simple fixes — the upstream maintainer is responsive to PRs.

### Primary branch

`main`
