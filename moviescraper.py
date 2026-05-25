import logging
import multiprocessing
import os
import re
import sys
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
    fetch_stored_links,
    get_connection,
    insert_movie,
    insert_ongoing,
    insert_series,
    insert_zip,
    load_existing_images,
)
from src.helpers import detect_resolution, parse_season
from src.introspect import filter_stored
from src.notify import notify_complete, notify_error, notify_links, notify_no_season

load_dotenv()

log = logging.getLogger(__name__)

_EP_RE = re.compile(r"s(\d+)e(\d+)", re.IGNORECASE)


def setup_logging(verbose=False):
    """INFO = milestones only; DEBUG (--verbose) = every step."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    for noisy in ("httpx", "httpcore", "selenium", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _short(url, limit=64):
    """Compact URL for milestone lines: host + trimmed path. Full URL goes to DEBUG."""
    if not url:
        return "-"
    if len(url) <= limit:
        return url
    return f"{url[:limit]}...(truncated {len(url) - limit} chars)"


def _ep_tag(name_text, fallback):
    """s01e03 from a driveseed filename, else the positional fallback."""
    m = _EP_RE.search(name_text or "")
    return f"s{m.group(1)}e{m.group(2)}" if m else fallback

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


# Load existing images from DB (logged in __main__ after setup_logging)
_conn = get_connection(DB_PARAMS)
allimagesrcdb = load_existing_images(_conn)
_conn.close()


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
    log.debug("Landing flow start: %s (at %s)", _short(url), _short(driver.current_url))
    try:
        wait = WebDriverWait(driver, 30)
        timer = wait.until(EC.presence_of_element_located((By.ID, "timer")))
        if timer:
            log.debug("Landing flow: timer found, submitting landing form")
            driver.execute_script("document.getElementById('landing').submit();")
            wait = WebDriverWait(driver, 10)
            element = wait.until(
                EC.presence_of_element_located((By.ID, "verify_button2"))
            )
            if element:
                log.debug("Landing flow: verify_button2 found, clicking through")
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
                log.debug("Landing flow: GO TO DOWNLOAD found, clicking")
                driver.execute_script(
                    'document.getElementById("two_steps_btn").click()'
                )
            log.debug("Landing flow SUCCESS: now at %s", _short(driver.current_url))
            return True
    except TimeoutException:
        log.debug("Landing flow TIMEOUT waiting for timer/verify at %s", _short(driver.current_url))
        return False
    except Exception as e:
        log.debug("Landing flow FAILED for %s at %s: %s", _short(url), _short(driver.current_url), e)
        return False
    log.debug("Landing flow: no timer element at %s", _short(driver.current_url))
    return False


def _verify_final_link(driver):
    """Check if we landed on driveseed.org/file/. Returns True/False."""
    c_url_now = driver.current_url
    try:
        try16 = is_element_present(driver, By.CSS_SELECTOR, "a.navbar-brand")
    except Exception:
        try:
            try16 = is_element_present(driver, By.CSS_SELECTOR, "a.navbar-brand")
        except Exception:
            if driver.current_url.startswith("https://driveseed.org/file/"):
                try16 = True
            else:
                log.debug("Verify final link FAILED (no navbar-brand): %s", _short(driver.current_url))
                return False
    if not try16:
        log.debug("Verify final link FAILED (navbar-brand absent): %s", _short(c_url_now))
        return False
    c_url = driver.current_url
    if c_url == "https://driveseed.org/404":
        log.debug("Verify final link FAILED (404 page)")
        return False
    verdict = c_url.startswith("https://driveseed.org/file/")
    log.debug("Verify final link verdict for %s: %s", _short(c_url), verdict)
    return verdict


def _close_extra_tab(driver):
    window_handles = driver.window_handles
    log.debug("Open tabs: %d (at %s)", len(window_handles), _short(driver.current_url))
    if len(window_handles) == 2:
        driver.switch_to.window(driver.window_handles[0])
        driver.close()
        driver.switch_to.window(driver.window_handles[0])
        log.debug("Closed extra tab, back at %s", _short(driver.current_url))


def _navigate_with_retry(driver, url, retries=3):
    for attempt in range(1, retries + 1):
        try:
            driver.get(url)
            log.debug("Navigated to %s (attempt %d)", _short(url), attempt)
            return True
        except Exception as e:
            log.debug("Navigation attempt %d/%d failed for %s: %s", attempt, retries, _short(url), e)
    log.warning("Navigation FAILED after %d attempts: %s", retries, _short(url))
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
        log.debug("File info after refresh: %s", name_text)
    resolution = detect_resolution(name_text)
    log.debug("Resolution detect: %r from %r", resolution, name_text[:120])
    return resolution, name_text


def _process_episode_download(
    driver, episodedownloadlink, ongoingseries, allscrapedepisodes
):
    """Navigate through episode download links and return (direct_links, captions)."""
    allepidirectlinks = []
    captions = []
    season_encountered = set()

    total = len(episodedownloadlink)
    log.debug("Episode path: %d links to process", total)
    for n, epi_url in enumerate(episodedownloadlink, 1):
        tag = f"E{n:02d}/{total}"
        log.info("Resolving %s...", tag)
        if not _navigate_with_retry(driver, epi_url):
            log.info("FAIL %s navigation failed", tag)
            continue

        landed = _handle_landing_page(driver, epi_url)
        if not landed:
            log.debug("Retrying landing flow for %s", _short(epi_url))
            landed = _handle_landing_page(driver, epi_url)
        log.debug("Landing flow final result for %s: %s", _short(epi_url), landed)

        _close_extra_tab(driver)

        if not _verify_final_link(driver):
            log.info("FAIL %s verify failed", tag)
            continue

        c_url = driver.current_url
        allepidirectlinks.append(c_url)
        if ongoingseries:
            allscrapedepisodes.append(c_url)

        resolution, name_text = _detect_resolution_from_page(driver)

        season = parse_season(name_text)
        log.debug("Season parsed: %r (seen so far: %s)", season, sorted(season_encountered))
        if season and season not in season_encountered:
            season_encountered.add(season)
            captions.append(f"\n\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\nSeason {season}")

        if resolution:
            captions.append(
                f"\n{_resolution_display_name(resolution)} - {c_url}"
            )
            log.info("OK %s %s %s", tag, _ep_tag(name_text, f"ep{n}"), resolution)
        else:
            log.info("FAIL %s no resolution matched", tag)

    log.debug("Episode path done: %d direct links, %d caption blocks", len(allepidirectlinks), len(captions))
    if ongoingseries:
        log.debug("Scraped %d episodes for ongoing series", len(allscrapedepisodes))

    return allepidirectlinks, captions


# Zip download path
def _process_zip_download(driver, zipfilelinks, downloadlinks):
    """Navigate through zip download links and return (direct_links, captions, unbroken)."""
    allzipdirectlinks = []
    captions = []
    season_encountered = set()
    unbrokenlink = False

    total = len(zipfilelinks)
    log.debug("Zip path: %d links to process", total)
    for n, zip_url in enumerate(zipfilelinks, 1):
        tag = f"ZIP{n}/{total}" if total > 1 else "ZIP"
        log.info("Resolving %s...", tag)
        if zip_url.startswith(f"{MOVIEMOD_BASE_URL}download"):
            log.debug("Skipping internal download URL: %s", _short(zip_url))
            continue

        if not _navigate_with_retry(driver, zip_url):
            log.info("FAIL %s navigation failed", tag)
            continue

        # find fast-server-gdrive button
        which_button = None
        try:
            fds = driver.find_element(
                By.CSS_SELECTOR,
                "a.maxbutton-1.maxbutton.maxbutton-fast-server-gdrive",
            )
            which_button = "maxbutton-1"
        except Exception:
            try:
                fds = driver.find_element(
                    By.CSS_SELECTOR,
                    "a.maxbutton-3.maxbutton.maxbutton-fast-server-gdrive",
                )
                which_button = "maxbutton-3"
            except Exception:
                log.warning("Could not find zip file link: %s", _short(downloadlinks))
                continue
        log.debug("Zip button matched: %s", which_button)

        fdsl = fds.get_attribute("href")
        log.debug("Zip file shortlink: %s", fdsl)
        try:
            driver.get(fdsl)
            log.debug("Loaded shortlink, now at %s", _short(driver.current_url))
        except Exception as e:
            if "ERR_CONNECTION_CLOSED" in str(e):
                driver.get(fdsl)
                log.debug("Page refreshed due to ERR_CONNECTION_CLOSED in fdsl")

        landed = _handle_landing_page(driver, fdsl)
        log.debug("Landing flow result for zip shortlink: %s", landed)
        _close_extra_tab(driver)

        if not _verify_final_link(driver):
            log.info("FAIL %s verify failed", tag)
            continue

        c_url = driver.current_url
        allzipdirectlinks.append(c_url)
        unbrokenlink = True

        resolution, name_text = _detect_resolution_from_page(driver)

        season = parse_season(name_text)
        log.debug("Season parsed: %r (seen so far: %s)", season, sorted(season_encountered))
        if season and season not in season_encountered:
            season_encountered.add(season)
            captions.append(f"\n\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\u2605\nSeason {season}")

        if resolution:
            captions.append(
                f"\n{_resolution_display_name(resolution)} - {c_url}"
            )
            log.info("OK %s %s", tag, resolution)
        else:
            log.info("FAIL %s no resolution matched", tag)

    log.debug("Zip path done: %d direct links, %d caption blocks, unbroken=%s",
              len(allzipdirectlinks), len(captions), unbrokenlink)
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

        log.info("Resolving movie button...")
        log.debug("Download button link: %s", _short(btn_url))
        if not _navigate_with_retry(driver, btn_url):
            log.info("FAIL movie button navigation failed")
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
            log.warning("gddl not present: %s", _short(btn_url))
            continue

        gddlh = gddl.get_attribute("href")
        try:
            driver.get(gddlh)
        except Exception as e:
            if "ERR_CONNECTION_CLOSED" in str(e):
                driver.get(gddlh)
                log.debug("Page refreshed due to ERR_CONNECTION_CLOSED in gddlh")

        _handle_landing_page(driver, gddlh)
        _close_extra_tab(driver)

        if not _verify_final_link(driver):
            continue

        c_url = driver.current_url
        log.debug("Final movie URL: %s", _short(c_url))
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
def process_download_link(
    thread_id,
    imagesrc,
    link_queue,
    allongoing,
    chrome_options,
    only_episode_urls=None,
    only_zip_urls=None,
    only_button_urls=None,
    scope="all",
    episode_indices=None,
    skip_dedup=False,
    send_links=False,
):
    try:
        driver = webdriver.Chrome(options=chrome_options)
        while not link_queue.empty():
            ongoingseries = False
            ongoingseriesepilist = {}
            allscrapedepisodes = []
            downloadlinks = link_queue.get(block=False)
            imagesourceurl = imagesrc.get(block=False)
            if imagesourceurl in allimagesrcdb and not skip_dedup:
                log.debug("Already scraped, skipping: %s", _short(imagesourceurl))
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
                log.debug("Description: %s", movie_descrp)
            except (ValueError, Exception):
                extracted_text = []
                movie_info = driver.find_elements(By.XPATH, "//p[strong]")
                for info in movie_info:
                    extracted_text.append(info.text)
                result = "\n".join(extracted_text)
                starti = result.index("Name")
                endi = result.index("Size")
                movie_descrp = result[starti:endi]
                log.debug("Description: %s", movie_descrp)

            series = "Season" in result
            theatreprint = "HDCaM" in result
            title_t0 = time.time()
            title_name = movie_descrp.strip().splitlines()[0] if movie_descrp.strip() else downloadlinks

            # SERIES path
            if series and not anime:
                log.info("--- Series: %s ---", title_name)
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
                if only_zip_urls is not None:
                    zipfilelinks = [u for u in zipfilelinks if u in only_zip_urls]
                    log.debug("Pre-filtered to %d chosen zip links", len(zipfilelinks))
                log.debug("checkzip=%s, zip buttons found: %d", checkzip, len(zipfilelinks))

                if not zipfilelinks and scope in ("all", "zip"):
                    log.info("SKIP no zip buttons, skipping title")
                    continue

                seriesdownloadlink = []
                sdbutton = driver.find_elements(
                    By.CSS_SELECTOR,
                    "a.maxbutton-23.maxbutton.maxbutton-episode-links",
                )
                log.debug("Episode-link buttons (maxbutton-23): %d", len(sdbutton))
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
                if only_episode_urls is not None:
                    seriesdownloadlink = [u for u in seriesdownloadlink if u in only_episode_urls]
                    log.debug("Pre-filtered to %d chosen episode links", len(seriesdownloadlink))
                log.debug("Series download links collected: %d", len(seriesdownloadlink))

                captions = []
                allepidirectlinks = []
                if scope == "zip":
                    log.debug("Scope is zip-only, skipping episode links")
                    seriesdownloadlink = []
                for sd_link in seriesdownloadlink:
                    if sd_link.startswith(f"{MOVIEMOD_BASE_URL}download"):
                        log.debug("Skipping internal download URL: %s", _short(sd_link))
                        continue
                    if not _navigate_with_retry(driver, sd_link):
                        log.warning("Error loading series link: %s", _short(sd_link))
                        continue
                    # Site dropped the darkmysite_* classes; match episode
                    # anchors by href prefix instead (same filter as before).
                    epidl = driver.find_elements(
                        By.CSS_SELECTOR,
                        "a[href^='https://cloud.unblockedgames.world/?']",
                    )
                    log.debug("Raw episode anchors on page: %d (at %s)", len(epidl), _short(driver.current_url))
                    for e in epidl[:10]:
                        log.debug("Raw episode anchor href: %r", e.get_attribute("href"))
                    episodedownloadlink = [
                        href
                        for href in (e.get_attribute("href") for e in epidl)
                        if href
                    ]
                    log.debug("Episode downloads found: %d", len(episodedownloadlink))
                    if scope == "specific" and episode_indices is not None:
                        episodedownloadlink = [
                            u for i, u in enumerate(episodedownloadlink) if i in episode_indices
                        ]
                        log.debug("Specific-episode filter: %d links left", len(episodedownloadlink))

                    if ongoingseries:
                        allscrapedepisodes.extend(episodedownloadlink)

                    ep_links, ep_captions = _process_episode_download(
                        driver,
                        episodedownloadlink,
                        ongoingseries,
                        allscrapedepisodes,
                    )
                    log.info("Episode batch done: %d links, %d captions", len(ep_links), len(ep_captions))
                    allepidirectlinks.extend(ep_links)
                    captions.extend(ep_captions)

                if ongoingseries:
                    ongoingseriesepilist[checker] = [allscrapedepisodes]

                series_row = None
                if allepidirectlinks:
                    final_captions = "".join(captions)
                    log.debug("Captions:\n%s", final_captions)
                    conn = get_connection(DB_PARAMS)
                    try:
                        series_row = insert_series(
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
                    log.info("OK series #%s, %d episodes", series_row, len(allepidirectlinks))
                else:
                    log.debug("No episode direct links, skipping series DB insert")

                zip_row, zip_links = None, []
                if checkzip and scope in ("all", "zip"):
                    zip_links, zip_captions, zip_unbroken = _process_zip_download(
                        driver, zipfilelinks, downloadlinks
                    )
                    log.debug("Zip totals: %d links, %d captions, unbroken=%s",
                              len(zip_links), len(zip_captions), zip_unbroken)
                    if zip_unbroken:
                        fullcaption = movie_descrp + "".join(zip_captions)
                        log.debug("Full zip caption:\n%s", fullcaption)
                        allzdirectlinks = "\n".join(zip_links)

                        if STAR not in fullcaption:
                            notify_no_season(
                                TELEGRAM_BOT_TOKEN,
                                TELEGRAM_GROUP_CHAT_ID,
                                movie_descrp,
                                allzdirectlinks,
                            )

                        conn = get_connection(DB_PARAMS)
                        try:
                            zip_row = insert_zip(conn, imagesourceurl, fullcaption, allzdirectlinks)
                        finally:
                            conn.close()
                        log.info("OK zip #%s, %d links", zip_row, len(zip_links))

                title_secs = time.time() - title_t0
                parts = []
                if allepidirectlinks:
                    parts.append(f"{len(allepidirectlinks)} episodes (series #{series_row})")
                if zip_links:
                    parts.append(f"{len(zip_links)} zip (zip #{zip_row})")
                summary = ", ".join(parts) if parts else "nothing stored"
                log.info("DONE %s | %s | %ds", title_name, summary, int(title_secs))
                final_links = allepidirectlinks + zip_links
                for link in final_links:
                    log.info("  %s", link)
                if final_links and send_links:
                    notify_links(TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_CHAT_ID, title_name, final_links)

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
                    if only_button_urls is not None:
                        buttonlinks = [u for u in buttonlinks if u in only_button_urls]
                        log.debug("Pre-filtered to %d chosen buttons", len(buttonlinks))

                    mov_links, mov_caption, mov_unbroken = _process_movie_download(
                        driver, buttonlinks
                    )

                    if mov_unbroken:
                        allmdirectlinks = "\n".join(mov_links)

                        final_caption = movie_descrp + f"\n{STAR}" + mov_caption
                        all_captions = final_caption

                        conn = get_connection(DB_PARAMS)
                        try:
                            movie_row = insert_movie(conn, imagesourceurl, all_captions, allmdirectlinks)
                        finally:
                            conn.close()
                        title_secs = time.time() - title_t0
                        log.info("DONE %s | movie #%s, %d links | %ds",
                                 title_name, movie_row, len(mov_links), int(title_secs))
                        for link in mov_links:
                            log.info("  %s", link)
                        if send_links:
                            notify_links(TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_CHAT_ID, title_name, mov_links)
                    else:
                        log.info("FAIL %s, no working movie links", title_name)

            elif series and anime:
                log.debug("Anime series skipped: %s", title_name)
            elif not series:
                log.debug("Anime title skipped: %s", title_name)

    except TimeoutException:
        pass
    except Exception as e:
        log.exception("Error in process_download_link")
        notify_error(TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_CHAT_ID, str(e))


BANNER = """
███╗   ███╗ ██████╗ ██╗   ██╗██╗███████╗███╗   ███╗ ██████╗ ██████╗ ███████╗
████╗ ████║██╔═══██╗██║   ██║██║██╔════╝████╗ ████║██╔═══██╗██╔══██╗██╔════╝
██╔████╔██║██║   ██║██║   ██║██║█████╗  ██╔████╔██║██║   ██║██║  ██║███████╗
██║╚██╔╝██║██║   ██║╚██╗ ██╔╝██║██╔══╝  ██║╚██╔╝██║██║   ██║██║  ██║╚════██║
██║ ╚═╝ ██║╚██████╔╝ ╚████╔╝ ██║███████╗██║ ╚═╝ ██║╚██████╔╝██████╔╝███████║
╚═╝     ╚═╝ ╚═════╝   ╚═══╝  ╚═╝╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝

███████╗ ██████╗██████╗  █████╗ ██████╗ ███████╗██████╗
██╔════╝██╔════╝██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗
███████╗██║     ██████╔╝███████║██████╔╝█████╗  ██████╔╝
╚════██║██║     ██╔══██╗██╔══██║██╔═══╝ ██╔══╝  ██╔══██╗
███████║╚██████╗██║  ██║██║  ██║██║     ███████╗██║  ██║
╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝
"""


def build_chrome_options():
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
    return chrome_options


def run_pages(start_page, end_page, num_processes):
    """Phase 1: scrape pages. Returns (images, links, ongoing) manager lists."""
    imagesrc = multiprocessing.Manager().list()
    downloadlinks = multiprocessing.Manager().list()
    allongoing = multiprocessing.Manager().list()

    lock = multiprocessing.Manager().Lock()
    pool = multiprocessing.Pool(processes=num_processes)
    pool.starmap(scraping, [(start_page, end_page, imagesrc, downloadlinks, allongoing, lock)])
    pool.close()
    pool.join()

    log.info("Scraped %d images, %d download links, %d ongoing",
             len(imagesrc), len(downloadlinks), len(allongoing))
    return imagesrc, downloadlinks, allongoing


def run_single(req):
    """Process one SingleRequest through the phase-2 pipeline (single worker).

    When links are already stored and this isn't a forced refresh, skip the
    browser entirely: print + send the stored links instead.
    """
    if not req.refresh:
        conn = get_connection(DB_PARAMS)
        try:
            stored = fetch_stored_links(conn, req.image_url)
        finally:
            conn.close()
        links = filter_stored(
            stored, req.scope, req.season, req.quality, req.episode_indices
        )
        if not links and stored:
            log.info(
                "Stored links don't cover this request (scope=%s season=%s quality=%s), scraping fresh",
                req.scope, req.season, req.quality,
            )
        if links:
            use_stored = True
            if sys.stdin.isatty():
                from src.interactive import ask_stored_or_fresh

                choice = ask_stored_or_fresh(len(links))
                if choice is None:
                    log.info("Nothing selected, exiting")
                    return
                use_stored = choice == "stored"
            if use_stored:
                title = req.title or req.post_url
                log.info("DONE %s | %d stored links (skipped scrape)", title, len(links))
                for link in links:
                    log.info("  %s", link)
                notify_links(TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_CHAT_ID, title, links)
                return
    link_queue = multiprocessing.Queue()
    link_queue.put(req.post_url)
    imagesrc_queue = multiprocessing.Queue()
    imagesrc_queue.put(req.image_url)
    allongoing = [req.post_url] if req.ongoing else []
    chrome_options = build_chrome_options()
    start_time = time.time()
    process_download_link(
        0, imagesrc_queue, link_queue, allongoing, chrome_options,
        only_episode_urls=req.episode_urls, only_zip_urls=req.zip_urls,
        only_button_urls=req.button_urls, scope=req.scope,
        episode_indices=req.episode_indices, skip_dedup=True,
        send_links=True,
    )
    total_time = time.time() - start_time
    log.info("Single-title run done in %.1f seconds", total_time)
    notify_complete(TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_CHAT_ID, total_time)


def _parse_args(argv=None):
    import argparse

    parser = argparse.ArgumentParser(prog="moviescraper", description="MovieMod scraper")
    common = argparse.ArgumentParser(add_help=False)
    # SUPPRESS: a subparser default of False would clobber `-v` given
    # before the subcommand, so the inherited flag only writes when present.
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS,
                        help="show every step (DEBUG); default shows milestones only")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show every step (DEBUG); default shows milestones only")
    sub = parser.add_subparsers(dest="cmd")
    p_pages = sub.add_parser("pages", parents=[common], help="mass scrape a page range")
    p_pages.add_argument("--start", type=int, default=START_PAGE)
    p_pages.add_argument("--end", type=int, default=END_PAGE)
    p_pages.add_argument("-p", "--processes", type=int, default=NUM_PROCESSES)
    p_search = sub.add_parser("search", parents=[common], help="search and scrape one title")
    p_search.add_argument("query", nargs="?", default=None)
    p_search.add_argument("--pick", type=int, default=None,
                          help="result index (skips arrow menu)")
    p_search.add_argument("--season", default=None, help="season number (skips prompt)")
    p_search.add_argument("--resolution", default=None,
                          help="quality label, e.g. 720px264 (skips prompt)")
    p_search.add_argument("--scope", default=None,
                          choices=["all", "episodes", "specific", "zip"],
                          help="what to fetch (skips prompt)")
    p_search.add_argument("--episodes", default=None,
                          help="episode numbers for scope=specific, e.g. 1-3,5")
    p_search.add_argument("--refresh", action="store_true",
                          help="re-scrape even when stored links exist")
    # Set AFTER add_subparsers (it resets cmd to None). cmd stays None
    # when no subcommand is given so __main__ can tell "no args" apart
    # from an explicit `pages` call; everything else gets safe defaults.
    parser.set_defaults(
        query=None, pick=None, season=None, resolution=None,
        scope=None, episodes=None, refresh=False,
        start=START_PAGE, end=END_PAGE, processes=NUM_PROCESSES,
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_args()
    setup_logging(args.verbose)
    print(BANNER)
    log.info("Starting moviemod-scraper")
    log.info("Resolved base URL: %s", MOVIEMOD_BASE_URL)
    log.info("Loaded %d existing images from DB", len(allimagesrcdb))

    if args.cmd is None:
        if sys.stdin.isatty():
            from src import interactive as _ix

            mode = _ix.ask_mode()
            args.cmd = "search" if mode.startswith("search") else "pages"
        else:
            args.cmd = "pages"  # headless (e.g. compose up): mass scrape, no prompts

    if getattr(args, "cmd", None) == "search":
        from src import interactive as _ix

        req = _ix.run_search_flow(
            MOVIEMOD_BASE_URL, args.query, args.pick,
            args.season, args.resolution, args.scope, args.episodes,
        )
        if req is None:
            log.info("Nothing selected, exiting")
        else:
            req.refresh = args.refresh
            run_single(req)
    else:
        # --- Phase 1: scrape pages for image URLs + download links ---
        num_processes = getattr(args, "processes", NUM_PROCESSES)
        start_page = getattr(args, "start", START_PAGE)
        end_page = getattr(args, "end", END_PAGE)

        imagesrc, downloadlinks, allongoing = run_pages(start_page, end_page, num_processes)

        # --- Phase 2: process each download link ---
        chrome_options = build_chrome_options()

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

