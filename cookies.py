import pickle
import os
from datetime import datetime

def save_cookies(driver, filename="cookies.pkl"):
    cookies = driver.get_cookies()
    with open(filename, "wb") as f:
        pickle.dump(cookies, f)
    print(f"Cookies 已保存到 {filename}")

def load_cookies(driver, filename="cookies.pkl"):
    if not os.path.exists(filename):
        print("Cookie 文件不存在")
        return False
    with open(filename, "rb") as f:
        cookies = pickle.load(f)
    for cookie in cookies:
        driver.add_cookie(cookie)
    print("Cookies 已载入")
    return True
