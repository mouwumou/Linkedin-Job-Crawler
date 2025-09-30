from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
import threading
import queue
import time
import argparse
import random

from crawler import login_linkedin_driver, CrawlerJob, result_router, linkedin_page_crawler
from url_generator import generate_urls
from cookies import save_cookies, load_cookies

CHROME_DRIVER_PATH = ChromeDriverManager().install()

LOGIN_CHECK_URL = "https://www.linkedin.com/feed/"
LOGIN_STATUS_KEYWORDS = ("login", "checkpoint")

def _is_session_active(driver) -> bool:
    auth_cookie = driver.get_cookie("li_at")
    if not auth_cookie:
        return False
    expiry = auth_cookie.get("expiry")
    if expiry and expiry <= time.time():
        return False
    current_url = (driver.current_url or "").lower()
    if any(keyword in current_url for keyword in LOGIN_STATUS_KEYWORDS):
        return False
    if driver.find_elements(By.ID, "username"):  # 登录页的用户名输入框
        return False
    return True

def ensure_driver_logged_in(driver, cookies_file: str, *, check_url: str = LOGIN_CHECK_URL) -> None:
    if _is_session_active(driver):
        return
    if check_url:
        driver.get(check_url)
        time.sleep(2)
        if _is_session_active(driver):
            return
    print("Detected invalid LinkedIn session, attempting to re-login...")
    driver.delete_all_cookies()
    if not login_linkedin_driver(driver):
        raise RuntimeError("Automatic LinkedIn login failed; please verify credentials")
    save_cookies(driver, cookies_file)
    driver.refresh()
    time.sleep(3)
    if not _is_session_active(driver):
        raise RuntimeError("LinkedIn session still invalid after login")



def init_driver(
    cookies_file: str = "cookies.pkl",
    *,
    headless: bool = False,
    page_load_timeout: float | None = 60.0,
):
    options = Options()

    # 初始化 WebDriver
    options.add_argument("disable-blink-features=AutomationControlled")

    # 伪造请求头
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.114 Safari/537.36 Edg/103.0.1264.49"
    )

    # 隐藏“正受到自动测试软件的控制”提示
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    # 禁用自动化扩展
    # options.add_experimental_option("useAutomationExtension", False)

    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-gpu")

    # 初始化 WebDriver
    driver = webdriver.Chrome(service=Service(CHROME_DRIVER_PATH), options=options)
    if page_load_timeout and page_load_timeout > 0:
        driver.set_page_load_timeout(page_load_timeout)
    driver.get("https://www.linkedin.com")  # 必须先打开域名才能加 cookie


    # 载入 cookie
    cookies_loaded = load_cookies(driver, cookies_file)
    if cookies_loaded:
        driver.refresh()
        time.sleep(3)  # 等待页面刷新完成
    else:
        print("No valid cookies found; performing interactive login")
        driver.delete_all_cookies()
        if not login_linkedin_driver(driver):
            raise RuntimeError("Automatic LinkedIn login failed; please verify credentials")
        save_cookies(driver, cookies_file)
        driver.refresh()
        time.sleep(3)

    ensure_driver_logged_in(driver, cookies_file)

    return driver


def worker(
    worker_id,
    job_queue,
    results,
    results_lock,
    *,
    cookies_file="cookies.pkl",
    headless=False,
    sleep_min=2.0,
    sleep_max=7.0,
    max_attempts=3,
    retry_backoff=10.0,
    page_load_timeout=60.0,
):
    driver = init_driver(
        cookies_file,
        headless=headless,
        page_load_timeout=page_load_timeout,
    )
    try:
        while True:
            job = job_queue.get(timeout=20) 
            try:
                ensure_driver_logged_in(driver, cookies_file)
                if sleep_max > 0:
                    delay = random.uniform(sleep_min, max(sleep_min, sleep_max))
                    if delay > 0:
                        time.sleep(delay)

                data = job.handler(driver, job.url, time_sleep=3, wait_time=60) # set a longer wait_time to ensure not affected by anti-bot
                if data is None:
                    raise RuntimeError("handler returned empty result")

                # use result_router to handle the result
                result_router(data, job_queue, results, results_lock)
                job.attempts = 0
                print(f"len(results)={len(results)}")
                print(
                    f"[Worker {worker_id}] Finished job: {job.url} Remaining jobs: {job_queue.qsize()}"
                )
            except Exception as exc:  # noqa: BLE001
                job.attempts += 1
                if job.attempts < max_attempts:
                    backoff = min(retry_backoff * job.attempts, retry_backoff * 4)
                    print(
                    print(f"[Worker {worker_id}] Job failed {job.url} ({exc}), retry {job.attempts} scheduled in {backoff:.1f}s")
                    )
                    time.sleep(backoff)
                    job_queue.put(job)
                else:
                    print(
                    print(f"[Worker {worker_id}] Job permanently failed {job.url} ({exc}) after maximum retries")
                    )
            finally:
                job_queue.task_done()
    except queue.Empty:
        pass
    finally:
        driver.quit()
        print(f"[Worker {worker_id}] finished")


def run_crawler(
    jobs,
    num_workers=3,
    *,
    cookies_file="cookies.pkl",
    headless=False,
    sleep_min=2.0,
    sleep_max=5.0,
    max_attempts=3,
    retry_backoff=10.0,
    page_load_timeout=60.0,
):
    """Run crawler dispatcher"""
    job_queue = queue.Queue()
    results: list[dict] = []
    results_lock = threading.Lock()

    for job in jobs:
        job_queue.put(job)

    threads = []
    for i in range(num_workers):
        t = threading.Thread(
            target=worker,
            args=(i, job_queue, results, results_lock),
            kwargs={
                "cookies_file": cookies_file,
                "headless": headless,
                "sleep_min": sleep_min,
                "sleep_max": sleep_max,
                "max_attempts": max_attempts,
                "retry_backoff": retry_backoff,
                "page_load_timeout": page_load_timeout,
            },
        )
        t.start()
        threads.append(t)

    # 等待所有任务完成
    job_queue.join()

    # 等待所有线程退出
    for t in threads:
        t.join()

    return results

def save_results(results, output_file="results.json"):
    import json
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"Results saved to {output_file}")

def main(args):
    # 载入args
    keywords = args.keywords
    states = args.states
    num_workers = args.workers
    sleep_min = args.sleep_min
    sleep_max = args.sleep_max
    max_attempts = args.max_attempts
    retry_backoff = args.retry_backoff
    headless = args.headless
    cookies_file = args.cookies_file
    page_load_timeout = args.page_timeout

    if sleep_max < sleep_min:
        sleep_max = sleep_min


    # 生成爬虫队列
    urls = generate_urls(keyword=keywords, states=states)
    jobs = [CrawlerJob(url, linkedin_page_crawler) for url in urls]

    # 运行爬虫
    results = run_crawler(
        jobs,
        num_workers,
        cookies_file=cookies_file,
        headless=headless,
        sleep_min=sleep_min,
        sleep_max=sleep_max,
        max_attempts=max_attempts,
        retry_backoff=retry_backoff,
        page_load_timeout=page_load_timeout,
    )
    print(f"爬取完成，共获得 {len(results)} 条结果")

    # 保存结果
    save_results(results)

    # 退出
    print("所有任务完成，退出")
    

if __name__ == "__main__":
    args = argparse.ArgumentParser(description="LinkedIn Job Crawler")
    args.add_argument("--keywords", type=str, required=True, help="Search keyword")
    args.add_argument("--states", type=str, nargs="+", help="States to crawl; default is all")
    args.add_argument("--workers", type=int, default=3, help="Number of worker threads (default 3)")
    args.add_argument("--sleep-min", type=float, default=2.0, help="Minimum delay before each job in seconds")
    args.add_argument("--sleep-max", type=float, default=5.0, help="Maximum delay before each job in seconds")
    args.add_argument("--max-attempts", type=int, default=3, help="Maximum retries per job")
    args.add_argument("--retry-backoff", type=float, default=10.0, help="Base retry backoff in seconds")
    args.add_argument("--headless", action="store_true", help="Run Chrome in headless mode")
    args.add_argument("--cookies-file", type=str, default="cookies.pkl", help="Path to cookies file")
    args.add_argument("--page-timeout", type=float, default=60.0, help="Page load timeout in seconds")
    args = args.parse_args()

    print("Args:", args)
    main(args)
# Example usage:
# python main.py --keywords "Software Engineer" --states "California" "New York" --workers 5
# python main.py --keywords "Data Center" --states "Texas" --workers 1
