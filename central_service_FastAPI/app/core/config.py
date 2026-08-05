"""应用配置。"""

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import URL


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def get_required_setting(name: str) -> str:
    """读取必需的环境变量。

    参数:
        name: 环境变量名称。
    返回:
        去除首尾空白后的环境变量值。
    """
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"缺少必需配置: {name}")
    return value


WECHAT_TOKEN = get_required_setting("WECHAT_TOKEN")
WECHAT_ENCODING_AES_KEY = get_required_setting("WECHAT_ENCODING_AES_KEY")
WECHAT_APP_ID = get_required_setting("WECHAT_APP_ID")
WECHAT_APP_SECRET = get_required_setting("WECHAT_APP_SECRET")
IP_LOOKUP_API_KEY = get_required_setting("IP_LOOKUP_API_KEY")

MYSQL_HOST = get_required_setting("MYSQL_HOST")
MYSQL_PORT = int(get_required_setting("MYSQL_PORT"))
MYSQL_DATABASE = get_required_setting("MYSQL_DATABASE")
MYSQL_USER = get_required_setting("MYSQL_USER")
MYSQL_PASSWORD = get_required_setting("MYSQL_PASSWORD")

DATABASE_URL = URL.create(
    drivername="mysql+pymysql",
    username=MYSQL_USER,
    password=MYSQL_PASSWORD,
    host=MYSQL_HOST,
    port=MYSQL_PORT,
    database=MYSQL_DATABASE,
    query={"charset": "utf8mb4"},
)
