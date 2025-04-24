from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import datetime
import time
import logging
import argparse
import config
import random
import os
import sys
import platform
import pickle
import ntplib
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 存储cookies的文件路径
COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies.pkl")
MAX_NTP_RETRY = 5  # NTP时间同步最大重试次数
NETWORK_DELAY = 0.3  # 预估网络延迟时间（秒）


class TimeSync:
    """网络时间同步工具类"""

    @staticmethod
    def get_network_time():
        """获取NTP服务器时间"""
        for _ in range(MAX_NTP_RETRY):
            try:
                client = ntplib.NTPClient()
                response = client.request("pool.ntp.org", version=3)
                return datetime.datetime.fromtimestamp(response.tx_time)
            except Exception as e:
                logger.warning(f"NTP同步失败: {str(e)}")
                time.sleep(0.5)

        logger.warning("无法获取网络时间，将使用本地时间")
        return datetime.datetime.now()


def save_cookies(driver):
    """保存当前会话的cookies到文件"""
    try:
        cookies = driver.get_cookies()
        with open(COOKIES_FILE, "wb") as f:
            pickle.dump(cookies, f)
        logger.info(f"成功保存登录状态到 {COOKIES_FILE}")
        return True
    except Exception as e:
        logger.error(f"保存cookies失败: {e}")
        return False


def load_cookies(driver, url):
    """从文件加载cookies并应用到当前会话"""
    if not os.path.exists(COOKIES_FILE):
        logger.info("没有找到保存的登录状态")
        return False

    try:
        # 先访问目标域名，否则无法添加cookies
        domain = url.split("//")[1].split("/")[0]
        base_url = f"{url.split('//')[0]}//{domain}"
        driver.get(base_url)

        # 加载cookies
        with open(COOKIES_FILE, "rb") as f:
            cookies = pickle.load(f)

        for cookie in cookies:
            # 有些cookie可能缺少某些必要属性，需要进行处理
            try:
                if "expiry" in cookie:
                    cookie["expiry"] = int(cookie["expiry"])
                driver.add_cookie(cookie)
            except Exception as e:
                logger.debug(f"添加cookie失败: {e}")
                continue

        logger.info("成功加载登录状态")

        # 刷新页面应用cookies
        driver.refresh()
        return True
    except Exception as e:
        logger.error(f"加载cookies失败: {e}")
        return False


def clear_cookies():
    """清除保存的cookies文件"""
    if os.path.exists(COOKIES_FILE):
        try:
            os.remove(COOKIES_FILE)
            logger.info(f"已清除保存的登录状态: {COOKIES_FILE}")
            return True
        except Exception as e:
            logger.error(f"清除登录状态失败: {e}")
            return False
    else:
        logger.info("没有找到保存的登录状态")
        return True


def setup_driver():
    """设置并返回WebDriver，添加反爬虫措施"""
    options = webdriver.ChromeOptions()
    # 添加选项以避免被检测为自动化工具
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    try:
        # 使用指定的ChromeDriver路径
        chrome_driver_path = ".chromedriver"
        logger.info(f"使用指定的ChromeDriver路径: {chrome_driver_path}")

        # 确保chromedriver有执行权限
        if os.path.exists(chrome_driver_path):
            os.chmod(chrome_driver_path, 0o755)

        service = Service(executable_path=chrome_driver_path)
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        logger.error(f"使用指定ChromeDriver路径失败: {e}")
        logger.info("尝试使用WebDriver Manager...")

        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e2:
            logger.error(f"使用WebDriver Manager失败: {e2}")
            logger.info("尝试使用系统默认ChromeDriver...")

            # 尝试直接使用系统默认的ChromeDriver
            driver = webdriver.Chrome(options=options)

    # 修改navigator.webdriver为undefined，进一步防止被检测
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    # 设置窗口大小随机化，减少特征识别
    width = random.randint(1000, 1200)
    height = random.randint(800, 1000)
    driver.set_window_size(width, height)

    return driver


def precise_wait(target_time):
    """精准等待到目标时间（精确到毫秒）"""
    logger.info(f"开始时间同步校准，目标时间: {target_time}")

    try:
        # 获取校准后的本地时间
        network_time = TimeSync.get_network_time()
        local_time = datetime.datetime.now()
        time_diff = network_time - local_time
        logger.info(
            f"时间校准完成，网络时间与本地时间差: {time_diff.total_seconds():.3f}秒"
        )
    except Exception as e:
        logger.error(f"时间同步失败: {str(e)}")
        time_diff = datetime.timedelta(0)  # 无法同步则不做调整

    while True:
        calibrated_time = datetime.datetime.now() + time_diff
        remaining = (target_time - calibrated_time).total_seconds() - NETWORK_DELAY

        if remaining <= 0:
            logger.info("到达抢单时间，开始操作！")
            return

        # 动态休眠控制
        if remaining > 1:
            sleep_time = min(remaining / 2, 1)
            if int(remaining) % 10 == 0:  # 每10秒显示一次日志
                logger.info(f"剩余时间 {remaining:.3f}s，休眠 {sleep_time:.3f}s")
            time.sleep(sleep_time)
        else:
            # 最后1秒使用忙等待保证精度
            time.sleep(0.001)


def optimized_refresh(driver):
    """优化版页面刷新策略"""
    try:
        # 使用JavaScript直接刷新避免重新加载静态资源
        driver.execute_script("location.reload(true);")

        # 智能等待页面核心元素加载
        WebDriverWait(driver, 1.5).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
        logger.debug("页面刷新完成")
    except Exception as e:
        logger.warning(f"页面刷新异常: {str(e)}")


def intelligent_click(driver, selectors, timeout=0.3):
    """智能点击策略（多选择器并行检测）"""
    script = """
    var selectors = arguments[0];
    for(var i=0; i<selectors.length; i++){
        var el = document.querySelector(selectors[i]);
        if(el && el.offsetParent !== null){
            el.click();
            return selectors[i];
        }
    }
    return false;
    """
    try:
        result = driver.execute_script(script, selectors)
        return result
    except Exception as e:
        logger.debug(f"JavaScript点击失败: {str(e)}")
        return False


def enhanced_grab(
    driver, buy_selectors, submit_selectors, max_retries=20, retry_interval=0.03
):
    """增强版抢单核心逻辑"""
    # 预热网络连接
    try:
        driver.execute_script("fetch('/')")
    except:
        pass

    # 时间窗口参数
    last_refresh = time.time()
    purchase_button_clicked = False

    for attempt in range(max_retries):
        current_time = time.time()

        # 如果未点击购买按钮，每0.5秒刷新页面
        if not purchase_button_clicked and current_time - last_refresh > 0.5:
            optimized_refresh(driver)
            last_refresh = current_time

        # 处理购买按钮点击
        if not purchase_button_clicked:
            clicked_selector = intelligent_click(driver, buy_selectors)
            if clicked_selector:
                logger.info(f"成功点击购买按钮！({clicked_selector})")
                purchase_button_clicked = True
                # 立即进行订单提交，不等待

        # 如果已点击购买按钮，尝试提交订单
        if purchase_button_clicked:
            if handle_order_submission(driver, submit_selectors):
                return True

        # 随机化重试间隔
        time.sleep(retry_interval * random.uniform(0.9, 1.1))

        if attempt % 5 == 0:
            logger.debug(f"抢单尝试 #{attempt+1}/{max_retries}")

    logger.warning("抢单操作超时")
    return False


def handle_order_submission(driver, submit_selectors, timeout=3):
    """处理订单提交环节"""
    deadline = time.time() + timeout  # 3秒提交超时
    while time.time() < deadline:
        clicked_selector = intelligent_click(driver, submit_selectors)
        if clicked_selector:
            logger.info(f"订单提交成功！({clicked_selector})")
            return True

        # 检查是否跳转到支付页面
        current_url = driver.current_url
        if any(key in current_url for key in ["pay", "confirm", "buy", "order"]):
            logger.info(f"检测到页面跳转: {current_url}")
            return True

        time.sleep(0.05)

    return False


def wait_for_time(target_time):
    """等待直到目标时间"""
    # 使用新的精准等待替代旧的等待方式
    precise_wait(target_time)


def try_click_button(driver, css_selector, wait_time=2):
    """尝试点击特定CSS选择器的按钮"""
    try:
        # 添加随机延迟模拟人类操作
        time.sleep(random.uniform(0.05, 0.2))
        button = WebDriverWait(driver, wait_time).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector))
        )
        button.click()
        logger.info(f"成功点击按钮: {css_selector}")
        return True
    except (TimeoutException, NoSuchElementException) as e:
        logger.debug(f"无法找到或点击按钮: {css_selector}")
        return False


def grab_order(driver, button_selectors, max_attempts=100, interval=0.1):
    """抢单主流程 - 先点击购买按钮，然后立即点击提交订单按钮"""
    # 使用增强版抢单逻辑替代原有逻辑
    return enhanced_grab(
        driver, button_selectors, config.SUBMIT_ORDER_SELECTORS, max_attempts, interval
    )


def parse_time(time_str):
    """解析时间字符串为datetime对象"""
    try:
        return datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        try:
            return datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            raise ValueError(
                "时间格式不正确，请使用 YYYY-MM-DD HH:MM:SS 或 YYYY-MM-DD HH:MM:SS.fff 格式"
            )


def check_login_status(driver):
    """检查是否已经登录"""
    try:
        # 尝试查找常见的登录状态元素（如用户昵称、购物车等）
        login_indicators = [
            "span.tb-login-info",  # 淘宝登录信息
            ".member-nick",  # 会员昵称
            ".site-nav-login-info",  # 登录信息区
        ]

        for indicator in login_indicators:
            elements = driver.find_elements(By.CSS_SELECTOR, indicator)
            if elements and len(elements) > 0:
                return True

        # 如果没有找到登录标识，则认为未登录
        return False
    except Exception as e:
        logger.debug(f"检查登录状态出错: {e}")
        return False


def main():
    # Global declaration needs to be at the beginning of the function
    global NETWORK_DELAY

    # 直接定义URL和时间（硬编码）
    TARGET_URL = "https://detail.tmall.hk/hk/item.htm?from=cart&id=573515891033"
    # TARGET_URL = "https://detail.tmall.hk/hk/item.htm?from=cart&id=779887795782"

    TARGET_TIME = datetime.datetime(2025, 4, 24, 15, 0, 0)

    # 添加特定的"立即购买"按钮选择器
    SPECIFIC_BUY_BUTTON = "a[title='立即购买']"

    # 仍然保留命令行参数解析，但以硬编码的值为默认值
    parser = argparse.ArgumentParser(description="淘宝/天猫自动抢单工具")
    parser.add_argument("--url", help="商品页面URL", default=TARGET_URL)
    parser.add_argument(
        "--time", help="抢单时间 (格式: YYYY-MM-DD HH:MM:SS[.fff])", default=None
    )
    parser.add_argument(
        "--selectors", help="自定义CSS选择器列表，用逗号分隔", default=None
    )
    parser.add_argument(
        "--max-attempts", type=int, help="最大尝试次数", default=config.MAX_ATTEMPTS
    )
    parser.add_argument(
        "--interval", type=float, help="重试间隔(秒)", default=config.RETRY_INTERVAL
    )
    parser.add_argument(
        "--clear-cookies", action="store_true", help="清除保存的登录状态后退出"
    )
    parser.add_argument(
        "--network-delay", type=float, help="网络延迟补偿(秒)", default=NETWORK_DELAY
    )
    args = parser.parse_args()

    # 设置网络延迟补偿
    NETWORK_DELAY = args.network_delay
    logger.info(f"设置网络延迟补偿为: {NETWORK_DELAY:.3f}秒")

    # 检查是否需要清除cookies
    if args.clear_cookies:
        clear_cookies()
        return

    # 优先使用命令行参数中的URL，否则使用硬编码的URL
    url = args.url

    # 处理抢单时间
    if args.time:
        target_time = parse_time(args.time)
    else:
        # 使用硬编码的时间
        target_time = TARGET_TIME
        logger.info(f"使用预设时间: {target_time.strftime('%Y-%m-%d %H:%M:%S')}")

    # 处理自定义CSS选择器
    if args.selectors:
        button_selectors = args.selectors.split(",")
    else:
        # 将特定按钮选择器添加到默认选择器列表的前面，优先尝试点击
        button_selectors = [SPECIFIC_BUY_BUTTON] + config.BUTTON_CSS_SELECTORS
        logger.info(f"添加了特定的天猫国际'立即购买'按钮选择器: {SPECIFIC_BUY_BUTTON}")
        logger.info("设置完成提交订单按钮选择器，抢购后将立即提交订单")

    # 初始化浏览器
    driver = setup_driver()
    driver.maximize_window()

    try:
        # 打开网页
        logger.info(f"正在打开页面: {url}")
        driver.get(url)

        # 尝试加载保存的cookies
        login_successful = load_cookies(driver, url)

        # 再次访问目标URL
        driver.get(url)

        # 验证登录状态
        if login_successful and check_login_status(driver):
            logger.info("检测到已成功登录，无需手动登录")
        else:
            # 清除无效的cookies
            if os.path.exists(COOKIES_FILE):
                logger.info("保存的登录状态已失效")
                clear_cookies()

            # 等待用户手动登录
            logger.info("请在浏览器中手动登录（如需要），准备好后按Enter继续...")
            input()

            # 检查是否成功登录
            if check_login_status(driver):
                logger.info("检测到成功登录，正在保存登录状态...")
                save_cookies(driver)
            else:
                logger.warning("未检测到成功登录，登录状态将不会被保存")

        # 等待到指定时间
        wait_for_time(target_time)

        # 开始抢单
        success = grab_order(driver, button_selectors, args.max_attempts, args.interval)

        if success:
            logger.info("抢单操作成功完成！请检查订单状态")
        else:
            logger.warning("抢单操作未成功完成，请手动检查")

        # 等待用户手动关闭
        logger.info(
            "抢单流程已完成，请检查结果。浏览器将保持打开状态，请手动关闭浏览器窗口或按Enter键退出程序..."
        )
        input()

    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"发生错误: {str(e)}")
    finally:
        if input("按Enter键关闭浏览器并退出程序，或输入任意内容保持浏览器打开: "):
            logger.info("保持浏览器打开状态，程序退出")
        else:
            logger.info("关闭浏览器并退出程序")
            driver.quit()


if __name__ == "__main__":
    main()
