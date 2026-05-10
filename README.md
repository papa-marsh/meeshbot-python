# MeeshBot

GroupMe bot powered by Claude. Receives webhook events, responds to messages, and handles slash commands. Runs in Docker on a mac mini.

Built with Python 3.14, FastAPI, Postgres, APScheduler, and uv.

## Features

**AI replies** — evaluates every incoming message to decide whether to respond, then generates a reply using Claude Sonnet with web search available. Uses a two-stage pipeline: a cheap classifier scores response likelihood before the heavier responder runs.

**Slash commands** — extensible command dispatch. Current commands:

| Command | Description |
|---|---|
| `/remindme <time> - <message>` | Set a reminder; time is parsed via LLM (natural language works) |
| `/reminders` | List pending reminders |
| `/scoreboard` | Message count leaderboard for the current group |
| `/scoreboard-all` | All-time leaderboard across all groups |
| `/roll` | Roll a dice |
| `/ping` | Health check |
| `/help` | List available commands |

**Message persistence** — all messages are synced to Postgres on receipt, providing history for AI context windows and scoreboard queries. A nightly job backfills the last 7 days from the GroupMe API.

## Running

```bash
just deploy       # build and start (runs migrations automatically)
just logs         # tail logs
just shell        # IPython shell inside the running container
just pull-deploy  # git pull + deploy (used in production)
```
