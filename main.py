from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import threading
import queue
import time
import argparse
import random

from crawler import login_linkedin_driver, CrawlerJob, result_router, linkedin_page_crawler
from url_generator import generate_urls
from cookies import save_cookies, load_cookies

CHROME_DRIVER_PATH = ChromeDriverManager().install()


def init_driver(
    cookies_file: str = "cookies.pkl",
    *,
    headless: bool = False,
    page_load_timeout: float | None = 30.0,
):
    options = Options()

    # 禁止浏览器检测自动化行为
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
    if load_cookies(driver, cookies_file):
        driver.refresh()
        time.sleep(3)  # 等待页面刷新完成
    else:
        print("没有 cookies，需要人工登录")
        # 如果第一次跑，需要人工登录并保存 cookie
        login_linkedin_driver(driver)
        save_cookies(driver, cookies_file)
        driver.refresh()
        time.sleep(3)

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
    sleep_max=5.0,
    max_attempts=3,
    retry_backoff=10.0,
    page_load_timeout=30.0,
):
    driver = init_driver(
        cookies_file,
        headless=headless,
        page_load_timeout=page_load_timeout,
    )
    try:
        while True:
            job = job_queue.get(timeout=60)
            try:
                if sleep_max > 0:
                    delay = random.uniform(sleep_min, max(sleep_min, sleep_max))
                    if delay > 0:
                        time.sleep(delay)

                data = job.handler(driver, job.url, time_sleep=3, wait_time=10)
                if data is None:
                    raise RuntimeError("handler 返回空结果")

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
                        f"[Worker {worker_id}] 任务失败 {job.url} ({exc}), 第 {job.attempts} 次重试，{backoff:.1f}s 后重排队"
                    )
                    time.sleep(backoff)
                    job_queue.put(job)
                else:
                    print(
                        f"[Worker {worker_id}] 任务最终失败 {job.url} ({exc})，已达到最大重试次数"
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
    page_load_timeout=30.0,
):
    """运行爬虫调度"""
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
    args.add_argument("--keywords", type=str, required=True, help="搜索关键词")
    args.add_argument("--states", type=str, nargs="+", help="要爬取的州，默认全部")
    args.add_argument("--workers", type=int, default=3, help="并发线程数，默认3")
    args.add_argument("--sleep-min", type=float, default=2.0, help="每个任务前的最小等待秒数")
    args.add_argument("--sleep-max", type=float, default=5.0, help="每个任务前的最大等待秒数")
    args.add_argument("--max-attempts", type=int, default=3, help="单个任务最大重试次数")
    args.add_argument("--retry-backoff", type=float, default=10.0, help="任务失败后的基础退避秒数")
    args.add_argument("--headless", action="store_true", help="以 headless 模式运行浏览器")
    args.add_argument("--cookies-file", type=str, default="cookies.pkl", help="cookies 文件路径")
    args.add_argument("--page-timeout", type=float, default=30.0, help="页面加载超时时间(秒)")
    args = args.parse_args()

    print("参数:", args)
    main(args)
# Example usage:
# python main.py --keywords "Software Engineer" --states "California" "New York" --workers 5
# 以上命令会爬取加州和纽约的 Software Engineer 职位 信息，使用5个并发线程。
