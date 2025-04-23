# 默认目标URL
DEFAULT_URL = "https://www.taobao.com/"

# 默认按钮CSS选择器列表 - 根据常见淘宝/天猫按钮添加
BUTTON_CSS_SELECTORS = [
    # 淘宝常用购买按钮
    ".tb-btn-buy",
    ".J_LinkBuy",
    ".J_BuyNow",
    "a.J_LinkBuy",
    "a.tb-button",
    ".buynow",
    "#J_confirmBuy",
    # 天猫常用购买按钮
    "a[title='立即购买']",
    "button.tm-btn-primary[type='button']",
    ".tm-option[title='立即购买']",
    "#J_SecKill .btn-special",
    "#J_SecKill .btn-buyer",
    # 抢购按钮
    ".btn-special[title='立即抢购']",
    ".tb-btn-rush",
]

# 提交订单按钮
SUBMIT_ORDER_SELECTORS = [
    ".go-btn[title='提交订单']",  # 添加用户提供的精确选择器
    "a.go-btn[title='提交订单']",
    ".go-btn[title='提交订单']",
    "a[title='提交订单']",
    ".go-btn",
    "#J_submitOrder",
    ".submit-btn",
    "button[type='submit'][title='提交订单']",
    ".order-submit",
    ".submitOrder",
    ".action-submit"
]

# 最大尝试次数
MAX_ATTEMPTS = 100

# 重试间隔 (秒)
RETRY_INTERVAL = 0.01
