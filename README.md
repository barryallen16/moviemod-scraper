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

## Prerequisites

- Python 3.x
- MySQL Server
- ChromeDriver (for Selenium)

---

## Setup

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/barryallen16/moviemod-scraper.git
   cd moviemod-scraper
   ```

2. **Install Dependencies**:
   - Install the required Python libraries using `requirements.txt`:
     ```bash
     pip install -r requirements.txt
     ```

3. **Set Up Environment Variables**:
   - Create a `.env` file and add the following:
     ```plaintext
     TELEGRAM_BOT_TOKEN=your-telegram-bot-token
     TELEGRAM_GROUP_CHAT_ID=your-telegram-group-chat-id
     DB_HOST=your-database-host
     DB_USER=your-database-username
     DB_PASSWORD=your-database-password
     DB_NAME=your-database-name
     NUM_PROCESSES=2
     START_PAGE=1
     END_PAGE=5
     MOVIEMOD_BASE_URL=https://moviesmod.red/
     ```

4. **Set Up MySQL Database**:
   - Create the required tables using the provided SQL schema:
     ```sql
     CREATE DATABASE moviemod;

     USE moviemod;

     CREATE TABLE movies (
         id INT AUTO_INCREMENT PRIMARY KEY,
         image_url TEXT,
         caption TEXT,
         org_links TEXT
     );

     CREATE TABLE series (
         id INT AUTO_INCREMENT PRIMARY KEY,
         image_url TEXT,
         movie_descrp TEXT,
         links TEXT,
         org_links TEXT
     );

     CREATE TABLE ongoing (
         id INT AUTO_INCREMENT PRIMARY KEY,
         serieslink TEXT,
         episodelinks TEXT
     );

     CREATE TABLE zip (
         id INT AUTO_INCREMENT PRIMARY KEY,
         image_url TEXT,
         links TEXT,
         org_links TEXT
     );
     ```

5. **Run the Script**:
   ```bash
   python moviescraper.py
   ```

---

## Configuration

- **Environment Variables**:
  - `TELEGRAM_BOT_TOKEN`: Your Telegram bot token.
  - `TELEGRAM_GROUP_CHAT_ID`: The chat ID of the Telegram group for notifications.
  - `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`: MySQL database credentials.
  - `NUM_PROCESSES`: Number of processes for multiprocessing.
  - `START_PAGE`, `END_PAGE`: Range of pages to scrape.
  - `MOVIEMOD_BASE_URL`: Base URL of the MoviesMod website.

- **ChromeDriver**:
  - Ensure ChromeDriver is installed and added to your system's PATH.
---

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository.
2. Create a new branch for your feature or bugfix.
3. Commit your changes and push them to your fork.
4. Submit a pull request.

---

## License

This project is licensed under the **GNU General Public License v3.0**. See the [LICENSE](LICENSE) file for details.
