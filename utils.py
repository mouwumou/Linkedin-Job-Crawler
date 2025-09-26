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


def extract_number_results(ele):
    num_text = ele.find_element(By.CSS_SELECTOR, "header div.jobs-search-results-list__subtitle").text.strip()
    num = re.search(r'(\d[\d,]*)\s+results?', num_text)
    if num:
        return int(num.group(1).replace(",", ""))
    else:   
        return None

def safe_text(default=""):
    """装饰器：如果找不到元素就返回 default"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except NoSuchElementException:
                return default
            except AttributeError:
                return default
        return wrapper
    return decorator


@safe_text("")
def get_job_id(ele):
    # ele expected to be a job card element, so the id should located at li>div>div[data-job-id]
    job_id = ele.find_element(By.CSS_SELECTOR, "li>div>div[data-job-id]")
    return job_id.get_attribute("data-job-id")

@safe_text("")
def get_job_name(ele):
    job_name = ele.find_element(By.CSS_SELECTOR, "div.artdeco-entity-lockup__title>a>span")
    return job_name.text.strip()

@safe_text("")
def get_job_subtitle(ele):
    job_subtitle = ele.find_element(By.CSS_SELECTOR, "div.artdeco-entity-lockup__subtitle")
    return job_subtitle.text.strip()

@safe_text("")
def get_job_caption(ele):
    job_caption = ele.find_element(By.CSS_SELECTOR, "div.artdeco-entity-lockup__caption")
    return job_caption.text.strip()

@safe_text("")
def get_job_metadata(ele):
    job_metadata = ele.find_element(By.CSS_SELECTOR, "div.artdeco-entity-lockup__metadata")
    return job_metadata.text.strip()

@safe_text("")
def get_job_url(ele):
    job_url = ele.find_element(By.CSS_SELECTOR, "div.artdeco-entity-lockup__title>a")
    return job_url.get_attribute("href")

def extract_job_data(job_card):
    return {
        "job_id": get_job_id(job_card),
        "job_name": get_job_name(job_card),
        "company_name": get_job_subtitle(job_card),
        "job_location": get_job_caption(job_card),
        "job_metadata": get_job_metadata(job_card),
        "job_url": get_job_url(job_card)
    }