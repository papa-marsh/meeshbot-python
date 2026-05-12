shell:
    docker compose exec meeshbot uv run ipython -i meeshbot/shell.py

deploy:
    docker compose down && \
    docker compose up -d --build && \
    docker exec meeshbot uv run oxyde migrate && \
    uv sync && \
    sleep 1 && \
    just logs

logs:
    docker compose logs meeshbot

logs-f:
    docker compose logs -f meeshbot

pull-deploy:
    git checkout main && \
    git pull && \
    just deploy

pull-deploy-f:
    git checkout main && \
    git fetch origin && \
    git reset --hard origin/main && \
    git pull && \
    just deploy
