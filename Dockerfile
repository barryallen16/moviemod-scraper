# 1. Start with Python
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV UV_LINK_MODE=copy

# Install Google Chrome with aria2c (16 parallel connections > single wget).
# ChromeDriver is NOT installed on purpose: Selenium Manager (bundled with
# selenium>=4.6) resolves the matching driver at runtime. A pinned driver
# drifts from stable Chrome and breaks with SessionNotCreatedException.
RUN apt-get update \
    && apt-get install -y --no-install-recommends aria2 \
    && aria2c -x 16 -s 16 -o google-chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y -f ./google-chrome.deb \
    && rm google-chrome.deb \
    && apt-get purge -y aria2 \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY . .

CMD [".venv/bin/python", "moviescraper.py"]
