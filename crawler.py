import time, re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.keys import Keys

from url_generator import FULL_FILTER_DEFINITIONS, generate_urls, FULL_FILTER_ORDER, extend_url_with_filter
from utils import extract_number_results, extract_job_data

import os
from dotenv import load_dotenv


class CrawlerJob:
    # 一个(URL, handler)结构体，代表爬虫任务的一个单元。
    # url: 需要爬取的 URL
    # handler: 处理该 URL 的函数，函数签名为 func(driver, url, time_sleep, wait_time) -> CrawlerResult
    def __init__(self, url, handler):
        self.url = url
        self.handler = handler
        # self.result = None  # 爬取结果，handler 的返回值
        # self.error = None  # 爬取错误信息，handler 抛出的异常
        # self.attempts = 0  # 已尝试爬取次数
        # self.success = False  # 是否成功爬取

class CrawlerResult:
    def __init__(self, url, data=None, crawler_type=None):
        self.url = url
        self.data = data  # 爬取结果，handler 的返回值
        self.crawler_type = crawler_type  # choice of ['list', 'detail']


def result_router(result: CrawlerResult, job_queue, results, results_lock) -> None:
    if not result or not result.data:
        return
    # 根据 result 的内容决定下一步操作
    if result.crawler_type == 'list':
        # 解析出新的任务，加入队列
        # result.data 是 list[CrawlerJob]，每个 dict 包含 'url' 和 'handler' 键
        for job in result.data:
            job_queue.put(job)

    elif result.crawler_type == 'detail':
        # 直接保存结果
        with results_lock:
            # results 是一个 list，保存所有 detail 结果，把结果追加进去
            results.append({"url": result.url, "jobs": result.data})

    else:
        print(f"未知的结果类型: {result.crawler_type}")

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
    if not USERNAME or not PASSWORD:
        raise ValueError("请在 .env 文件中设置 LINKEDIN_USERNAME 和 LINKEDIN_PASSWORD 环境变量")
        
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
    
def login_linkedin_driver(driver):
    load_dotenv()
    USERNAME = os.getenv("LINKEDIN_USERNAME")
    PASSWORD = os.getenv("LINKEDIN_PASSWORD")
    if not USERNAME or not PASSWORD:
        raise ValueError("请在 .env 文件中设置 LINKEDIN_USERNAME 和 LINKEDIN_PASSWORD 环境变量")

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
        return True
    else:
        print("❌ Login may have failed.")
        return False
        
        
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

def get_linkedin_job_main_page(driver, url, time_sleep=1, wait_time=10):
    # 访问 LinkedIn 职位搜索主页面，返回 main#main 元素
    driver.get(url)
    time.sleep(time_sleep)

    job_main = wait_get_element(driver, "main#main", timeout=wait_time)
    if not job_main:
        return None

    return job_main

def linkedin_page_crawler(driver, url, time_sleep=1, wait_time=10) -> CrawlerResult:
    # 爬取 LinkedIn 页面，如果大于 1000 则生成批次(url, linkedin_page_crawler)到queue继续爬取，直到页面小于1000或者无法叠加筛选项。
    # 如果页面小于1000则生成对应的爬虫任务到queue，(url, linkedin_job_crawler)。每页显示25条职位，使用start参数翻页。
    # 返回值: CrawlerResult {url, list[CrawlerJob], 'list'} or CrawlerResult {url, list[CrawlerJob], 'detail'}

    def generate_paged_urls(base_url, total_jobs):
        paged_urls = []
        for start in range(0, total_jobs, 25):
            paged_url = f"{base_url}&start={start}"
            paged_urls.append(paged_url)
        return paged_urls

    print(f"访问页面: {url}")
    job_main = get_linkedin_job_main_page(driver, url, time_sleep, wait_time)
    if not job_main:
        return CrawlerResult(url, [], 'list')
    total_jobs = extract_number_results(job_main)
    if total_jobs is None:
        print("无法解析职位总数，跳过该页面")
        return CrawlerResult(url, [], 'list')
    print(f"Total jobs found: {total_jobs}")

    jobs = []

    if total_jobs > 1000:
        print("超过 1000 条，生成细化筛选的任务...")
        # 生成细化筛选的任务
        # 先检查已有的筛选项
        current_filters = re.findall(r"f\.[^&=]+", url)
        existing_filter_keys = set(f.split(".")[1] for f in current_filters)
        # 可用的细化筛选项
        available_filters = [f for f in FULL_FILTER_DEFINITIONS if f not in existing_filter_keys]
        if not available_filters:
            print("没有可用的细化筛选项，直接生成职位详情任务...")
            jobs.extend(CrawlerJob(url, linkedin_job_crawler) for url in generate_paged_urls(url, total_jobs))
            return CrawlerResult(url, jobs, 'list')

        # 如果有可用选项，则按照 FULL_FILTER_ORDER 顺序，选择第一个生成新的任务。只生成一个细化筛选任务，避免任务爆炸。
        next_filter = next((f for f in FULL_FILTER_ORDER if f in available_filters), None)
        
        if not next_filter:
            print("没有可用的细化筛选项，直接生成职位详情任务...")
            jobs.extend(CrawlerJob(url, linkedin_job_crawler) for url in generate_paged_urls(url, total_jobs))
            return CrawlerResult(url, jobs, 'list')

        # 生成细化筛选任务
        filtered_urls = extend_url_with_filter(url, next_filter)
        # 遍历所有可能的选项值，生成新的任务
        for filtered_url in filtered_urls:
            jobs.append(CrawlerJob(filtered_url, linkedin_page_crawler))

        return CrawlerResult(url, jobs, 'list')
    else:
        print("少于 1000 条，生成职位详情的任务...")
        jobs.extend(CrawlerJob(url, linkedin_job_crawler) for url in generate_paged_urls(url, total_jobs))
        return CrawlerResult(url, jobs, 'list')

def linkedin_job_crawler(driver, url, time_sleep=1, wait_time=10) -> CrawlerResult:
    # 爬取 LinkedIn 职位列表页，返回当前页面所有职位数据
    # 返回值: CrawlerResult {url, list[dict], 'detail'}
    page_data = get_linkedin_job_main_page(driver, url, time_sleep, wait_time)
    if not page_data:
        return CrawlerResult(url, [], 'detail')

    # Wait for the first job card to load
    if not wait_for_element(driver, "ul:first-of-type>li.ember-view div.artdeco-entity-lockup__metadata", timeout=wait_time):
        return CrawlerResult(url, [], 'detail')

    job_cards = page_data.find_elements(By.CSS_SELECTOR, "ul:first-of-type>li.ember-view")
    jobs = [extract_job_data(card) for card in job_cards]

    return CrawlerResult(url, jobs, 'detail')

def linkedin_job_detail_crawler(driver, url, time_sleep=1, wait_time=10):
    pass