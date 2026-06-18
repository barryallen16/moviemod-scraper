# 1. Start with Python
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install dependencies, Google Chrome, and ChromeDriver in a single RUN block
RUN apt update \
    && apt install -y wget unzip \
    && wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y -f ./google-chrome-stable_current_amd64.deb \
    && wget https://storage.googleapis.com/chrome-for-testing-public/149.0.7827.155/linux64/chromedriver-linux64.zip \
    && unzip chromedriver-linux64.zip \
    &&  mv  chromedriver-linux64/chromedriver /usr/local/bin/ \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf chromedriver-linux64 chromedriver-linux64.zip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "moviescraper.py"]