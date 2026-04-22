# MovieMod Scraper

A Python-based web scraper for extracting movie and series details, including download links and images, from the [MoviesMod](https://moviesmod.red/) website. The project uses **Selenium** for web scraping, **multiprocessing** for parallel execution, **MySQL** for data storage, and **Telegram** for real-time notifications.


---

![vlcsnap-2025-01-16-12h42m26s612](https://github.com/user-attachments/assets/c6a9e319-b6dd-44b7-a3cd-859c59888cab)

**Demo video sped up 4x.**
- note: code is run on headfull mode for demostration. code in repo is in headless mode

https://github.com/user-attachments/assets/8ab58885-8724-4059-9793-96fea4f3d916

## Features

- **Web Scraping**: Extracts movie/series details (titles, descriptions, image URLs, and download links).
- **Multiprocessing**: Scrapes multiple pages simultaneously for faster execution.
- **Database Integration**: Stores scraped data in a MySQL database.
- **Telegram Notifications**: Sends real-time updates and error alerts to a Telegram group.
- **Retry Mechanism**: Handles connection errors and timeouts gracefully.
- **Headless Mode**: Runs Selenium in headless mode for efficient scraping.

---

## Project Structure

```plaintext
moviemod-scraper/
├── src/
│   ├── helpers.py   # resolution + season parsing (pure functions)
│   ├── db.py        # MySQL connection + insert helpers
│   └── notify.py    # Telegram notifications
├── tests/
│   └── test_helpers.py
├── moviescraper.py  # scraping orchestration (Selenium + multiprocessing)
├── getCurrentDomain.py
├── init.sql         # table schema (database itself comes from MYSQL_DATABASE / DB_NAME)
├── pyproject.toml
├── Dockerfile
└── docker-compose.yaml
```

---

## Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) for deps and runs
- MySQL Server (or Docker)
- ChromeDriver on PATH (local runs only; the Docker image installs Chrome + ChromeDriver)

---

## Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/barryallen16/moviemod-scraper.git
   cd moviemod-scraper
   ```

2. **Install Dependencies**:
   ```bash
   uv sync
   ```

3. **Set Up Environment Variables**:
   - Copy `.env.example` to `.env` and fill in values:
     ```bash
     cp .env.example .env
     ```
   - Required keys: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_GROUP_CHAT_ID`, `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `NUM_PROCESSES`, `START_PAGE`, `END_PAGE`, `website_type` (`hollywood` or `bollywood`).
   - The base URL is resolved at runtime via `getCurrentDomain.py`, so there is no `MOVIEMOD_BASE_URL` key.
   - Under Docker Compose, set `DB_HOST=db` so the scraper reaches the `db` service.

4. **Set Up MySQL Database**:
   - Tables are created from [`init.sql`](init.sql). With Docker Compose the database itself is created automatically from `DB_NAME`.

5. **Run the Script**:
   ```bash
   uv run moviescraper.py
   ```

6. **Run Tests / Lint**:
   ```bash
   uv run pytest -q
   uv run ruff check src/ tests/ moviescraper.py
   ```

---

## Run with Docker Compose

```bash
docker compose up --build
```

- `db` is MySQL 8.0 with `init.sql` applied on first start; credentials come from `DB_NAME` / `DB_USER` / `DB_PASSWORD` in `.env`.
- `scraper` waits for `db` to be healthy, then runs `moviescraper.py` once and exits.
- `shm_size: 2gb` is required for headless Chrome stability.

---

## Configuration

- **Environment Variables**:
  - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token.
  - `TELEGRAM_GROUP_CHAT_ID`: The chat ID of the Telegram group for notifications.
  - `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: MySQL database credentials.
  - `NUM_PROCESSES`: Number of processes for multiprocessing.
  - `START_PAGE`, `END_PAGE`: Range of pages to scrape.
  - `website_type`: `hollywood` or `bollywood` (used to resolve the current domain).

- **ChromeDriver**:
  - Local runs: ensure ChromeDriver is installed and added to your system's PATH.
  - Docker runs: handled by the `Dockerfile`.
---
## Selenium setup in Cloud

```bash
apt update \
&& apt install -y wget unzip \
&& wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
&& apt-get install -y -f ./google-chrome-stable_current_amd64.deb \
&& wget https://storage.googleapis.com/chrome-for-testing-public/149.0.7827.155/linux64/chromedriver-linux64.zip \
&& unzip chromedriver-linux64.zip \
&&  mv  chromedriver-linux64/chromedriver /usr/local/bin/ \
&&  google-chrome --version \
&& chromedriver --version \
```

---
## License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.
