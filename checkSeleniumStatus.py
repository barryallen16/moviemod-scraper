import time
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium import webdriver
import os
import time
from getCurrentDomain import getCurrentDomainName

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(options=chrome_options)
url = getCurrentDomainName()
try:
    driver.get(url)
    fmovie = driver.find_element(
        By.CSS_SELECTOR, "article.latestPost > header > h2 > a"
    )
    print(fmovie.text)
    print("Selenium working")
except:
    print("Selenium not working.")
