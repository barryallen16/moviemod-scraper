# 1. Start with Python
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install Google Chrome. ChromeDriver is NOT pinned here on purpose:
# Selenium Manager (bundled with selenium>=4.6) resolves the matching
# driver at runtime. A pinned driver drifts from stable Chrome and breaks
# with SessionNotCreatedException (seen with Chrome 153 vs driver 149).
RUN apt-get update \
    && apt-get install -y --no-install-recommends wget \
    && wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y -f ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "moviescraper.py"]