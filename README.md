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
- **Interactive CLI**: Search a title, pick season / resolution / episodes with arrow menus, scrape only what you chose.

---

## Important: download links expire

The final `driveseed.org/file/…` links are **valid for only a few hours**. The site issues dynamic, per-access download tokens (that's what the long `?sid=…` parameters are), so a link scraped in the morning is dead by the evening.

- **Use links the same day you scrape them.** Don't archive them for later.
- The MySQL rows are a snapshot of *what was available*, not a permanent mirror — re-scrape a title to refresh its links.
- If a stored link 404s, just run the title again instead of debugging the scraper.

---

## Project Structure

```plaintext
moviemod-scraper/
├── src/
│   ├── helpers.py      # resolution + season parsing (pure functions)
│   ├── db.py           # MySQL connection + insert helpers
│   ├── notify.py       # Telegram notifications
│   ├── introspect.py   # detail-page parsing: qualities, sizes, seasons
│   └── interactive.py  # search resolver + arrow-menu prompts
├── tests/
│   ├── test_helpers.py
│   └── test_introspect.py
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
- Chrome browser (local runs only; the driver is auto-managed by Selenium Manager — see below)

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

5. **Run the Script**: see [CLI usage](#cli-usage) below. Quickest start:
   ```bash
   uv run moviescraper.py
   ```

6. **Run Tests / Lint**:
   ```bash
   uv run pytest -q
   uv run ruff check src/ tests/ moviescraper.py
   ```

---

## CLI usage

Two modes. With no arguments and an interactive terminal you get an arrow-key menu; without a terminal (e.g. `docker compose up`) it mass-scrapes headlessly.

| Command | What it does |
|---|---|
| `moviescraper.py` | Menu: mass scrape or search a single title (TTY only; headless falls back to mass) |
| `moviescraper.py pages --start 1 --end 5 -p 2` | Mass-scrape a page range (flags override `.env`) |
| `moviescraper.py search "last of us"` | Interactive: pick title → season → what to fetch → resolution (sizes shown) |
| `moviescraper.py search "last of us" --pick 0 --season 1 --resolution 720px264` | Same, fully headless (no menus) |

Single-title extras:

| Flag | Values | Meaning |
|---|---|---|
| `--pick N` | result index | Skips the title menu |
| `--season N` | e.g. `1` | Skips the season menu (series only) |
| `--resolution R` | `480p`, `720p`, `1080p`, `480px264`, `720px264`, `1080px264`, `720pbit`, `1080pbit` | Skips the resolution menu |
| `--scope S` | `all`, `episodes`, `specific`, `zip` | Everything / all episodes / chosen episodes / batch zip only |
| `--episodes R` | e.g. `1-3,5` | Episode numbers for `--scope specific` |
| `-v`, `--verbose` | flag | Show every scraping step (DEBUG); default shows milestones only |

What-to-fetch menu (series): `Everything (episodes + zip)` · `All episodes` · `Specific episodes` · `Zip file only`. Movies skip the season/scope menus — just resolution. Only the chosen variant goes through the browser; results land in MySQL and Telegram as usual, and the final links print at the end.

> **TTY note:** arrow menus need a real terminal. Under Docker use `docker compose run` (not `up`):
> ```bash
> docker compose run --rm scraper .venv/bin/python moviescraper.py search "last of us"
> ```
> Git Bash users: prefix with `winpty` if the menu doesn't render.

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
  - Not needed. Selenium Manager downloads the matching driver at runtime, locally and in Docker (Chrome itself is installed by the `Dockerfile`; locally, install the Chrome browser).
---
## Selenium setup in Cloud

```bash
apt-get update \
&& apt-get install -y wget \
&& wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
&& apt-get install -y -f ./google-chrome-stable_current_amd64.deb \
&& google-chrome --version
```

Do NOT install chromedriver manually. Selenium Manager (bundled with `selenium>=4.6`) downloads the matching driver at runtime. A manually pinned chromedriver drifts from Chrome upgrades and fails with `SessionNotCreatedException`.

---
## License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.
