import time, random, re, urllib.parse
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from getpass import getpass
from selenium.webdriver.common.keys import Keys

from functools import wraps

from utils import extract_number_results, extract_job_data
import os
from dotenv import load_dotenv


def wait_get_element(driver, selector, timeout=10):
    try:
        element = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        return element
    except TimeoutException:
        print(f"Timeout: Element with selector '{selector}' not found within {timeout} seconds.")
        return None
    
def wait_for_element(driver, selector, timeout=10):
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
        )
        return True
    except TimeoutException:
        print(f"Timeout: Element with selector '{selector}' not found within {timeout} seconds.")
        return False

def login_linkedin():
    load_dotenv()
    USERNAME = os.getenv("LINKEDIN_USERNAME")
    PASSWORD = os.getenv("LINKEDIN_PASSWORD")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    # login to LinkedIn login page
    driver.get("https://www.linkedin.com/login")
    time.sleep(2)

    # Enter email and password
    driver.find_element(By.ID, "username").send_keys(USERNAME)
    driver.find_element(By.ID, "password").send_keys(PASSWORD + Keys.RETURN)
    time.sleep(5)

    # Verify login
    if "feed" in driver.current_url or "jobs" in driver.current_url:
        print("✅ Login successful!")
        return True, driver
    else:
        print("❌ Login may have failed.")
        return False, driver
        
def linkedin_common_crawler(driver, url, time_sleep=1, wait_time=10):
    driver.get(url)
    time.sleep(time_sleep)

    job_main = wait_get_element(driver, "main#main", timeout=wait_time)
    if not job_main:
        return None

    # Wait for the first job card to load
    if not wait_for_element(driver, "ul:first-of-type>li.ember-view div.artdeco-entity-lockup__metadata", timeout=wait_time):
        return None
    
    job_card_list = job_main.find_elements(By.CSS_SELECTOR, "ul:first-of-type>li.ember-view")

    all_job_data = list(map(extract_job_data, job_card_list))

    return {
        "url": url,
        "jobs": all_job_data
    }