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
from selenium.webdriver.common.action_chains import ActionChains

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

def simulate_human_like_actions(driver, min_actions=1, max_actions=3):
    """Trigger a handful of small interactions to look less like a bot."""
    if not driver:
        return

    actions = [
        lambda: _random_pause(),
        lambda: _random_small_scroll(driver),
        lambda: _random_mouse_move(driver),
        lambda: _random_hover_focusable(driver),
        lambda: _random_keyboard_nudge(driver),
    ]

    min_actions = max(1, min(min_actions, len(actions)))
    max_actions = max(min_actions, min(max_actions, len(actions)))
    action_count = random.randint(min_actions, max_actions)

    for action in random.sample(actions, action_count):
        try:
            action()
        except Exception as exc:
            print(f"simulate_human_like_actions skipped action: {exc}")


def _random_pause():
    time.sleep(random.uniform(0.6, 2.4))


def _random_small_scroll(driver):
    offset = random.randint(-300, 400)
    if abs(offset) < 60:
        offset = 120 if offset >= 0 else -120
    driver.execute_script('window.scrollBy(arguments[0], arguments[1]);', 0, offset)
    time.sleep(random.uniform(0.2, 0.6))


def _random_mouse_move(driver):
    body = driver.find_element(By.TAG_NAME, 'body')
    x_offset = random.randint(-200, 200)
    y_offset = random.randint(-120, 120)
    if x_offset == 0 and y_offset == 0:
        x_offset = 35
    actions = ActionChains(driver)
    actions.move_to_element(body)
    actions.move_by_offset(x_offset, y_offset)
    actions.pause(random.uniform(0.1, 0.4))
    actions.perform()


def _random_hover_focusable(driver):
    selectors = [
        'a[href]',
        'button',
        '[role="button"]',
        'div[tabindex]',
        'input[type="text"]',
    ]
    candidates = []
    for selector in selectors:
        candidates.extend(driver.find_elements(By.CSS_SELECTOR, selector))
    visible = [el for el in candidates if el.is_displayed()]
    if not visible:
        return
    target = random.choice(visible)
    driver.execute_script('arguments[0].scrollIntoView({block: "center", inline: "center"});', target)
    ActionChains(driver).move_to_element(target).pause(random.uniform(0.3, 0.8)).perform()
    time.sleep(random.uniform(0.1, 0.5))


def _random_keyboard_nudge(driver):
    keys = [
        Keys.ARROW_DOWN,
        Keys.ARROW_UP,
        Keys.PAGE_DOWN,
        Keys.PAGE_UP,
    ]
    key = random.choice(keys)
    body = driver.find_element(By.TAG_NAME, 'body')
    ActionChains(driver).move_to_element(body).click().send_keys(key).perform()
    time.sleep(random.uniform(0.2, 0.5))
