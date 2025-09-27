from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import threading
import queue
import time
import argparse

from crawler import login_linkedin_driver, CrawlerJob, result_router, linkedin_page_crawler
from url_generator import generate_urls
from cookies import save_cookies, load_cookies


def init_driver(cookies_file="cookies.pkl"):
    # options = Options()

    # # 禁止浏览器检测自动化行为
    # options.add_argument("disable-blink-features=AutomationControlled")

    # # 伪造请求头
    # options.add_argument(
    #     "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/103.0.5060.114 Safari/537.36 Edg/103.0.1264.49"
    # )

    # # 隐藏“正受到自动测试软件的控制”提示
    # options.add_experimental_option("excludeSwitches", ["enable-automation"])

    # # 禁用自动化扩展
    # options.add_experimental_option("useAutomationExtension", False)

    # # 初始化 WebDriver
    # driver = webdriver.Chrome(options=options)
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
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


def worker(worker_id, job_queue, results, results_lock, cookies_file="cookies.pkl"):
    driver = init_driver(cookies_file)
    try:
        while True:
            job = job_queue.get(timeout=60)
            try:
                data = job.handler(driver, job.url, time_sleep=3, wait_time=10)
                # use result_router to handle the result
                result_router(data, job_queue, results, results_lock)
            finally:
                job_queue.task_done()
    except queue.Empty:
        pass
    finally:
        driver.quit()
        print(f"[Worker {worker_id}] finished")


def run_crawler(urls, num_workers=3):
    """运行爬虫调度"""
    job_queue = queue.Queue()
    results: list[dict] = []
    results_lock = threading.Lock()

    for url in urls:
        job_queue.put(url)

    threads = []
    for i in range(num_workers):
        t = threading.Thread(
            target=worker,
            args=(i, job_queue, results, results_lock),
            kwargs={"cookies_file": "cookies.pkl"},
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


    # 生成爬虫队列
    urls = generate_urls(keyword=keywords, states=states)
    jobs = [CrawlerJob(url, linkedin_page_crawler) for url in urls]

    # 运行爬虫
    results = run_crawler(jobs, num_workers)
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
    args = args.parse_args()

    print("参数:", args)
    main(args)
# Example usage:
# python main.py --keywords "Software Engineer" --states "California" "New York" --workers 5
# 以上命令会爬取加州和纽约的 Software Engineer 职位 信息，使用5个并发线程。
