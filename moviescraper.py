import logging
import multiprocessing
import os
import time

from dotenv import load_dotenv
from requests import Timeout
from retry import retry
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC  # noqa: N812
from selenium.webdriver.support.ui import WebDriverWait

from getCurrentDomain import getCurrentDomainName
from src.db import (
    get_connection,
    insert_movie,
    insert_ongoing,
    insert_series,
    insert_zip,
    load_existing_images,
)
from src.helpers import detect_resolution, parse_season
from src.notify import notify_complete, notify_error, notify_no_season

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_GROUP_CHAT_ID = os.getenv("TELEGRAM_GROUP_CHAT_ID")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
NUM_PROCESSES = int(os.getenv("NUM_PROCESSES", 2))
START_PAGE = int(os.getenv("START_PAGE", 1))
END_PAGE = int(os.getenv("END_PAGE", 1))
WEBSITE_TYPE = os.getenv("website_type", "hollywood")  # noqa: SIM112

MOVIEMOD_BASE_URL = getCurrentDomainName(website_type=WEBSITE_TYPE)

DB_PARAMS = {
    "host": DB_HOST,
    "user": DB_USER,
    "password": DB_PASSWORD,
    "database": DB_NAME,
}


# Helpers
def is_element_present(driver, by, value, timeout=10):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )
        return True
    except TimeoutException:
        return False


def _resolution_display_name(resolution):
    names = {
        "480p": "480p",
        "720p": "720p",
        "1080p": "1080p",
        "480px264": "480p x264",
        "720px264": "720p x264",
        "1080px264": "1080p x264",
        "720pbit": "720p 10Bit",
        "1080pbit": "1080p 10Bit",
    }
    return names.get(resolution, resolution)


# Load existing images from DB
_conn = get_connection(DB_PARAMS)
allimagesrcdb = load_existing_images(_conn)
_conn.close()
log.info("Loaded %d existing images from DB", len(allimagesrcdb))


# Page scraping
@retry((ConnectionError, Timeout, TimeoutException), tries=10, delay=2, backoff=2)
def scraping(start_page, end_page, imagesrc, downloadlinks, allongoing, lock):
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")  # comment this to run in headfull mode
    user_agent = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.92 Mobile Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")
    referer = MOVIEMOD_BASE_URL
    chrome_options.add_argument("--ignore-ssl-errors=yes")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument(f"referer={referer}")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--enable-javascript")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.add_argument("--enable-unsafe-swiftshader")
    driver = webdriver.Chrome(options=chrome_options)

    local_imagesrc = []
    local_downloadlinks = []
    local_allongoing = []

    for i in range(start_page, end_page + 1):
        formatted_url = f"{MOVIEMOD_BASE_URL}page/{i}"
        driver.get(formatted_url)

        div_elements = driver.find_elements(By.CLASS_NAME, "featured-thumbnail")
        counter = 0
        counterchecker = []
        for div_element in div_elements:
            mpsrc = div_element.find_element(By.TAG_NAME, "img").get_attribute("src")
            counter += 1
            if mpsrc in allimagesrcdb:
                counterchecker.append(counter)
                continue
            local_imagesrc.append(mpsrc)

        ml = driver.find_elements(By.CSS_SELECTOR, "h2.title.front-view-title")
        counter = 0
        for link in ml:
            mll = link.find_elements(By.CSS_SELECTOR, "a[href]")
            text = link.text
            for abc in mll:
                mdl = abc.get_attribute("href")
                counter += 1
                if counter in counterchecker:
                    continue
                local_downloadlinks.append(mdl)

            if "Added]" in text:
                local_allongoing.append(mdl)
        if (
            f"{MOVIEMOD_BASE_URL}download-superhero-movie-2008-comedy-movie-720p/"
            in local_downloadlinks
        ):
            break

    driver.quit()
    with lock:
        imagesrc.extend(local_imagesrc)
        downloadlinks.extend(local_downloadlinks)
        allongoing.extend(local_allongoing)


# Episode download path
def _handle_landing_page(driver, url, screenshot_tag=""):
    """Execute the landing/verify JS flow. Returns True on success."""
    try:
        wait = WebDriverWait(driver, 30)
        timer = wait.until(EC.presence_of_element_located((By.ID, "timer")))
        if timer:
            driver.execute_script("document.getElementById('landing').submit();")
            wait = WebDriverWait(driver, 10)
            element = wait.until(
                EC.presence_of_element_located((By.ID, "verify_button2"))
            )
            if element:
                driver.execute_script(
                    """var ubPopupContent = document.querySelector(".ub-popupcontent");
                    if (ubPopupContent) { ubPopupContent.style.display = "none"; }
                    var b2 = document.getElementById("verify_button2");
                    b2.style.visibility = "visible"; b2.dispatchEvent(new Event("click"));
                    var b3 = document.getElementById("verify_button");
                    b3.style.visibility = "visible"; b3.dispatchEvent(new Event("click"));
                    var b4 = document.getElementById("two_steps_btn");
                    b4.style.display = "block";"""
                )
            wait = WebDriverWait(driver, 10)
            element2 = wait.until(
                EC.presence_of_element_located((By.LINK_TEXT, "GO TO DOWNLOAD"))
            )
            if element2:
                driver.execute_script(
                    'document.getElementById("two_steps_btn").click()'
                )
            return True
    except TimeoutException:
        return False
    except Exception as e:
        log.debug("Landing page flow failed for %s: %s", url, e)
        return False
    return False


def _verify_final_link(driver):
    """Check if we landed on driveseed.org/file/. Returns True/False."""
    try:
        try16 = is_element_present(driver, By.CSS_SELECTOR, "a.navbar-brand")
    except Exception:
        try:
            try16 = is_element_present(driver, By.CSS_SELECTOR, "a.navbar-brand")
        except Exception:
            if driver.current_url.startswith("https://driveseed.org/file/"):
                try16 = True
            else:
                log.debug("Could not verify final link: %s", driver.current_url)
                return False
    if not try16:
        return False
    c_url = driver.current_url
    if c_url == "https://driveseed.org/404":
        return False
        return c_url.startswith("https://driveseed.org/file/")


def _close_extra_tab(driver):
    window_handles = driver.window_handles
    if len(window_handles) == 2:
        driver.switch_to.window(driver.window_handles[0])
        driver.close()
        driver.switch_to.window(driver.window_handles[0])


def _navigate_with_retry(driver, url, retries=3):
    for _attempt in range(retries):
        try:
            driver.get(url)
            return True
        except Exception:
            continue
    return False


def _detect_resolution_from_page(driver):
    """Get filename text from driveseed page and return (resolution, name_text)."""
    try:
        name_el = driver.find_element(By.CSS_SELECTOR, "li.list-group-item")
        name_text = name_el.text.lower()
    except Exception:
        driver.refresh()
        name_el = driver.find_element(By.CSS_SELECTOR, "li.list-group-item")
        name_text = name_el.text.lower()
        log.info("File info after refresh: %s", name_text)
    return detect_resolution(name_text), name_text


def _process_episode_download(
    driver, episodedownloadlink, ongoingseries, allscrapedepisodes
):
    """Navigate through episode download links and return (direct_links, captions)."""
    allepidirectlinks = []
    captions = []
    season_encountered = set()

    for epi_url in episodedownloadlink:
        if not _navigate_with_retry(driver, epi_url):
            log.warning("Could not load episode link: %s", epi_url)
            continue

        _handle_landing_page(driver, epi_url)
        _handle_landing_page(driver, epi_url)  # retry once more on failure

        _close_extra_tab(driver)

        if not _verify_final_link(driver):
            continue

        c_url = driver.current_url
        log.info("Final episode URL: %s", c_url)
        allepidirectlinks.append(c_url)
        if ongoingseries:
            allscrapedepisodes.append(c_url)

        resolution, name_text = _detect_resolution_from_page(driver)

        season = parse_season(name_text)
        if season and season not in season_encountered:
            season_encountered.add(season)
            captions.append(f"\n\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\nSeason {season}")

        if resolution:
            captions.append(
                f"\n{_resolution_display_name(resolution)} - {c_url}"
            )

    if ongoingseries:
        log.info("Scraped %d episodes for ongoing series", len(allscrapedepisodes))

    return allepidirectlinks, captions


# Zip download path
def _process_zip_download(driver, zipfilelinks, downloadlinks):
    """Navigate through zip download links and return (direct_links, captions, unbroken)."""
    allzipdirectlinks = []
    captions = []
    season_encountered = set()
    unbrokenlink = False

    for zip_url in zipfilelinks:
        if zip_url.startswith(f"{MOVIEMOD_BASE_URL}download"):
            continue

        if not _navigate_with_retry(driver, zip_url):
            continue

        # find fast-server-gdrive button
        try:
            fds = driver.find_element(
                By.CSS_SELECTOR,
                "a.maxbutton-1.maxbutton.maxbutton-fast-server-gdrive",
            )
        except Exception:
            try:
                fds = driver.find_element(
                    By.CSS_SELECTOR,
                    "a.maxbutton-3.maxbutton.maxbutton-fast-server-gdrive",
                )
            except Exception:
                log.warning("Could not find zip file link: %s", downloadlinks)
                continue

        fdsl = fds.get_attribute("href")
        log.info("Zip file shortlink: %s", fdsl)
        try:
            driver.get(fdsl)
        except Exception as e:
            if "ERR_CONNECTION_CLOSED" in str(e):
                driver.get(fdsl)
                log.info("Page refreshed due to ERR_CONNECTION_CLOSED in fdsl")

        _handle_landing_page(driver, fdsl)
        _close_extra_tab(driver)

        if not _verify_final_link(driver):
            continue

        c_url = driver.current_url
        log.info("Final zip URL: %s", c_url)
        allzipdirectlinks.append(c_url)
        unbrokenlink = True

        resolution, name_text = _detect_resolution_from_page(driver)

        season = parse_season(name_text)
        if season and season not in season_encountered:
            season_encountered.add(season)
            captions.append(f"\n\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\nSeason {season}")

        if resolution:
            captions.append(
                f"\n{_resolution_display_name(resolution)} - {c_url}"
            )

    return allzipdirectlinks, captions, unbrokenlink



# Movie download path

def _process_movie_download(driver, buttonlinks):
    """Navigate through movie download buttons and return (direct_links, caption, unbroken)."""
    allmoviedirectlinks = []
    unbrokenlink = False

    for btn_url in buttonlinks:
        if btn_url.startswith(f"{MOVIEMOD_BASE_URL}download"):
            continue
        if is_element_present(
            driver,
            By.CSS_SELECTOR,
            "a.maxbutton-1.maxbutton.maxbutton-download-links.custom-linethrough",
        ):
            continue

        log.info("Download button link: %s", btn_url)
        if not _navigate_with_retry(driver, btn_url):
            continue

        # find gdrive link button
        gddl = None
        if is_element_present(
            driver,
            By.CSS_SELECTOR,
            "a.maxbutton-2.maxbutton.maxbutton-google-drive-server-2",
        ):
            gddl = driver.find_element(
                By.CSS_SELECTOR,
                "a.maxbutton-2.maxbutton.maxbutton-google-drive-server-2",
            )
        else:
            try:
                try2 = is_element_present(
                    driver,
                    By.CSS_SELECTOR,
                    "a.maxbutton-2.maxbutton.maxbutton-gdrive-links-login",
                )
                if try2:
                    gddl = driver.find_element(
                        By.CSS_SELECTOR,
                        "a.maxbutton-2.maxbutton.maxbutton-gdrive-links-login",
                    )
            except Exception:
                pass

        if gddl is None:
            log.warning("gddl not present: %s", btn_url)
            continue

        gddlh = gddl.get_attribute("href")
        try:
            driver.get(gddlh)
        except Exception as e:
            if "ERR_CONNECTION_CLOSED" in str(e):
                driver.get(gddlh)
                log.info("Page refreshed due to ERR_CONNECTION_CLOSED in gddlh")

        _handle_landing_page(driver, gddlh)
        _close_extra_tab(driver)

        if not _verify_final_link(driver):
            continue

        c_url = driver.current_url
        log.info("Final movie URL: %s", c_url)
        allmoviedirectlinks.append(c_url)
        unbrokenlink = True

    # build caption from collected links
    caption = ""
    if unbrokenlink:
        resolution_links = {
            "480p": None, "720p": None, "1080p": None,
            "480p x264": None, "720p x264": None, "1080p x264": None,
            "720p 10Bit": None, "1080p 10Bit": None,
        }
        for link in allmoviedirectlinks:
            res, _ = _detect_resolution_from_page(driver)
            if res:
                display = _resolution_display_name(res)
                resolution_links[display] = link
        for display_name, link in resolution_links.items():
            if link:
                caption += f"\n{display_name} - {link}"

    return allmoviedirectlinks, caption, unbrokenlink



# Main download-link processor                                                 #

STAR = "\u2605" * 16  # ★★★★★★★★★★★★★★


@retry((ConnectionError, Timeout, TimeoutException), tries=10, delay=2, backoff=2)
def process_download_link(thread_id, imagesrc, link_queue, allongoing, chrome_options):
    try:
        driver = webdriver.Chrome(options=chrome_options)
        while not link_queue.empty():
            ongoingseries = False
            ongoingseriesepilist = {}
            allscrapedepisodes = []
            downloadlinks = link_queue.get(block=False)
            imagesourceurl = imagesrc.get(block=False)
            if imagesourceurl in allimagesrcdb:
                continue

            if not _navigate_with_retry(driver, downloadlinks):
                continue

            checker = downloadlinks
            if checker in allongoing:
                ongoingseries = True
                allscrapedepisodes = []

            # detect category
            category = driver.find_elements(
                By.CSS_SELECTOR, "div.thecategory a[href]"
            )
            anime = any(
                cat.get_attribute("href") == f"{MOVIEMOD_BASE_URL}anime/"
                for cat in category
            )

            # extract movie description
            try:
                list_items_with_strong = driver.find_elements(
                    By.XPATH, "//li[strong]"
                )
                text_items = [li.text for li in list_items_with_strong]
                result = "\n".join(text_items)
                starti = 5
                endi = result.index("Size")
                movie_descrp = result[starti:endi]
                log.info("Description: %s", movie_descrp)
            except (ValueError, Exception):
                extracted_text = []
                movie_info = driver.find_elements(By.XPATH, "//p[strong]")
                for info in movie_info:
                    extracted_text.append(info.text)
                result = "\n".join(extracted_text)
                starti = result.index("Name")
                endi = result.index("Size")
                movie_descrp = result[starti:endi]
                log.info("Description: %s", movie_descrp)

            series = "Season" in result
            theatreprint = "HDCaM" in result

            # SERIES path
            if series and not anime:
                log.info("Series found")
                driver.implicitly_wait(10)
                checkzip = is_element_present(
                    driver,
                    By.CSS_SELECTOR,
                    "a.maxbutton-24.maxbutton.maxbutton-batch-zip",
                )
                zipfilelinks = []
                if checkzip:
                    zipfileb = driver.find_elements(
                        By.CSS_SELECTOR,
                        "a.maxbutton-24.maxbutton.maxbutton-batch-zip",
                    )
                    zipfilelinks = [z.get_attribute("href") for z in zipfileb]

                if not zipfilelinks:
                    continue

                seriesdownloadlink = []
                sdbutton = driver.find_elements(
                    By.CSS_SELECTOR,
                    "a.maxbutton-23.maxbutton.maxbutton-episode-links",
                )
                if is_element_present(
                    driver,
                    By.CSS_SELECTOR,
                    "a.maxbutton-19.maxbutton.maxbutton-g-drive",
                ):
                    for el in driver.find_elements(
                        By.CSS_SELECTOR,
                        "a.maxbutton-19.maxbutton.maxbutton-g-drive",
                    ):
                        seriesdownloadlink.append(el.get_attribute("href"))
                for sdb in sdbutton:
                    seriesdownloadlink.append(sdb.get_attribute("href"))

                captions = []
                allepidirectlinks = []
                for sd_link in seriesdownloadlink:
                    if sd_link.startswith(f"{MOVIEMOD_BASE_URL}download"):
                        continue
                    if not _navigate_with_retry(driver, sd_link):
                        log.warning("Error loading series link: %s", sd_link)
                        continue

                    epidl = driver.find_elements(
                        By.CSS_SELECTOR,
                        "a.darkmysite_style_txt_border.darkmysite_style_link.darkmysite_processed",
                    )
                    episodedownloadlink = [
                        e.get_attribute("href")
                        for e in epidl
                        if e.get_attribute("href").startswith(
                            "https://tech.unblockedgames.world/?"
                        )
                    ]
                    log.info(
                        "Episode downloads found: %d", len(episodedownloadlink)
                    )

                    if ongoingseries:
                        allscrapedepisodes.extend(episodedownloadlink)

                    ep_links, ep_captions = _process_episode_download(
                        driver,
                        episodedownloadlink,
                        ongoingseries,
                        allscrapedepisodes,
                    )
                    allepidirectlinks.extend(ep_links)
                    captions.extend(ep_captions)

                if ongoingseries:
                    ongoingseriesepilist[checker] = [allscrapedepisodes]

                if allepidirectlinks:
                    log.info(
                        "All episode direct links: %s",
                        "\n".join(allepidirectlinks),
                    )

                if allepidirectlinks:
                    final_captions = "".join(captions)
                    log.info("Captions:\n%s", final_captions)
                    conn = get_connection(DB_PARAMS)
                    try:
                        insert_series(
                            conn,
                            imagesourceurl,
                            movie_descrp,
                            final_captions,
                            "\n".join(allepidirectlinks),
                        )
                        if ongoingseries:
                            for key, nested_values in ongoingseriesepilist.items():
                                nested_str = ", ".join(
                                    ", ".join(v) for v in nested_values
                                )
                                insert_ongoing(conn, key, nested_str)
                    finally:
                        conn.close()

                if checkzip:
                    log.info("Checking for zip files")
                    zip_links, zip_captions, zip_unbroken = _process_zip_download(
                        driver, zipfilelinks, downloadlinks
                    )
                    if zip_unbroken:
                        fullcaption = movie_descrp + "".join(zip_captions)
                        log.info(fullcaption)
                        allzdirectlinks = "\n".join(zip_links)
                        if allzdirectlinks:
                            log.info("All zip file links: %s", allzdirectlinks)

                        if STAR not in fullcaption:
                            notify_no_season(
                                TELEGRAM_BOT_TOKEN,
                                TELEGRAM_GROUP_CHAT_ID,
                                movie_descrp,
                                allzdirectlinks,
                            )

                        conn = get_connection(DB_PARAMS)
                        try:
                            insert_zip(conn, imagesourceurl, fullcaption, allzdirectlinks)
                        finally:
                            conn.close()

            # ================================================================ #
            # MOVIE path (not series, not anime)                               #
            # ================================================================ #
            elif not series and not anime:
                downloadbutton = driver.find_elements(
                    By.CSS_SELECTOR,
                    "a.maxbutton-1.maxbutton.maxbutton-download-links[href]",
                )
                if not theatreprint and downloadbutton:
                    driver.implicitly_wait(10)
                    buttonlinks = [b.get_attribute("href") for b in downloadbutton]

                    mov_links, mov_caption, mov_unbroken = _process_movie_download(
                        driver, buttonlinks
                    )

                    if mov_unbroken:
                        allmdirectlinks = "\n".join(mov_links)
                        if allmdirectlinks:
                            log.info(allmdirectlinks)

                        final_caption = movie_descrp + f"\n{STAR}" + mov_caption
                        all_captions = final_caption

                        conn = get_connection(DB_PARAMS)
                        try:
                            insert_movie(conn, imagesourceurl, all_captions, allmdirectlinks)
                        finally:
                            conn.close()

    except TimeoutException:
        pass
    except Exception as e:
        log.error("Error in process_download_link: %s", e)
        notify_error(TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_CHAT_ID, str(e))


if __name__ == "__main__":
    log.info("Starting moviemod-scraper")

    # --- Phase 1: scrape pages for image URLs + download links ---
    num_processes = NUM_PROCESSES
    start_page = START_PAGE
    end_page = END_PAGE

    imagesrc = multiprocessing.Manager().list()
    downloadlinks = multiprocessing.Manager().list()
    allongoing = multiprocessing.Manager().list()

    page_ranges = [(start_page, end_page)]

    lock = multiprocessing.Manager().Lock()
    pool = multiprocessing.Pool(processes=num_processes)
    pool.starmap(
        scraping,
        [
            (start, end, imagesrc, downloadlinks, allongoing, lock)
            for start, end in page_ranges
        ],
    )
    pool.close()
    pool.join()

    log.info("Scraped %d images, %d download links, %d ongoing",
             len(imagesrc), len(downloadlinks), len(allongoing))

    # --- Phase 2: process each download link ---
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")  # comment this to run in headfull mode
    user_agent = "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.5845.92 Mobile Safari/537.36"
    chrome_options.add_argument(f"user-agent={user_agent}")
    referer = MOVIEMOD_BASE_URL
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--enable-javascript")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.page_load_strategy = "eager"
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--enable-unsafe-swiftshader")
    chrome_options.add_argument(f"referer={referer}")

    link_queue = multiprocessing.Queue()
    for link in downloadlinks:
        link_queue.put(link)

    imagesrc_queue = multiprocessing.Queue()
    for image in imagesrc:
        imagesrc_queue.put(image)

    start_time = time.time()
    processes = []
    for i in range(num_processes):
        process = multiprocessing.Process(
            target=process_download_link,
            args=(i, imagesrc_queue, link_queue, allongoing, chrome_options),
        )
        processes.append(process)
        process.start()
    for process in processes:
        process.join()

    end_time = time.time()
    total_time = end_time - start_time
    log.info("Total time taken: %.1f seconds", total_time)
    notify_complete(TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_CHAT_ID, total_time)

