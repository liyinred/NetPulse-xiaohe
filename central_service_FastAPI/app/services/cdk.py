"""CDK 兑换码的内存状态、自动换码与兑换服务。"""

import asyncio
import logging
import re
import secrets
import threading
from dataclasses import dataclass, field
from time import time

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.user import UserLevel


CDK_TTL_SECONDS = 5 * 60
CDK_PREFIX = "CDK-"
CDK_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CDK_CODE_PATTERN = re.compile(r"^[A-HJ-NP-Z2-9]{16}$")
CDK_RETRY_DELAY_SECONDS = 5
CDK_MIN_ROTATION_DELAY_SECONDS = 0.05

REPLY_REDEEM_SUCCESS = "兑换成功，您已升级为高级用户，请刷新网页后生效。"
REPLY_ALREADY_PREMIUM = "您已是高级用户，无需兑换。"
REPLY_ALREADY_ADMIN = "您已是管理员，无需兑换。"
REPLY_USER_NOT_FOUND = "未找到账号，请先在网页扫码登录一次后再兑换。"
REPLY_ALREADY_REDEEMED = "您已兑换过该 CDK，请刷新网页后生效。"
REPLY_EXPIRED = "该 CDK 已过期，请向管理员获取新的 CDK。"
REPLY_INVALID = "CDK 无效，请检查后重新输入。"
REPLY_FORMAT_ERROR = "CDK 格式不正确，请按 `CDK-` + 16 位码的格式重新发送。"
REPLY_SYSTEM_BUSY = "系统繁忙，请稍后重试。"

logger = logging.getLogger(__name__)

_state_lock = threading.Lock()


@dataclass
class CdkState:
    """保存当前 CDK 及其有效期内已兑换的用户。

    属性:
        code: 当前 16 位兑换码。
        created_time: 生成时间（Unix 秒）。
        expire_time: 过期时间（Unix 秒）。
        redeemed_user_ids: 已使用当前码兑换成功的用户主键集合。
    """

    code: str
    created_time: int
    expire_time: int
    redeemed_user_ids: set[int] = field(default_factory=set)


@dataclass(frozen=True)
class CdkSnapshot:
    """当前 CDK 的只读快照，供接口返回使用。

    属性:
        code: 当前 16 位兑换码。
        created_time: 生成时间（Unix 秒）。
        expire_time: 过期时间（Unix 秒）。
        server_time: 生成快照时的服务端时间（Unix 秒）。
    """

    code: str
    created_time: int
    expire_time: int
    server_time: int


def _generate_code() -> str:
    """按去混淆字符集生成 16 位兑换码。

    参数:
        无。
    返回:
        由 ``CDK_ALPHABET`` 中字符组成的 16 位随机码。
    """
    return "".join(secrets.choice(CDK_ALPHABET) for _ in range(16))


def _build_state(current_time: int) -> CdkState:
    """根据指定时间创建一份新的 CDK 状态。

    参数:
        current_time: 新码的生成时间（Unix 秒）。
    返回:
        包含新码且兑换用户集合为空的状态对象。
    """
    return CdkState(
        code=_generate_code(),
        created_time=current_time,
        expire_time=current_time + CDK_TTL_SECONDS,
    )


# 模块导入即生成启动后的首个码，确保后台任务尚未开始轮询时已有有效码。
_state = _build_state(int(time()))


def get_cdk_snapshot(current_time: int | None = None) -> CdkSnapshot:
    """读取当前 CDK；已过期时先换新码再返回快照。

    参数:
        current_time: 可选的当前 Unix 秒时间戳，默认取系统时间。
    返回:
        当前码、生成时间、过期时间和服务端时间。
    """
    global _state
    with _state_lock:
        now = int(time()) if current_time is None else current_time
        if now >= _state.expire_time:
            _state = _build_state(now)
        return CdkSnapshot(
            code=_state.code,
            created_time=_state.created_time,
            expire_time=_state.expire_time,
            server_time=now,
        )


def _seconds_until_expire() -> float:
    """计算距离当前码过期还有多少秒。

    参数:
        无。
    返回:
        非负的剩余秒数；已过期时返回 0。
    """
    with _state_lock:
        return max(0.0, _state.expire_time - time())


def handle_cdk_text(raw_text: str, openid: str) -> str | None:
    """解析用户发送的微信文本并尝试兑换 CDK。

    参数:
        raw_text: 用户发送的原始文本。
        openid: 发送文本的微信用户 openid。
    返回:
        需要被动回复的文案；文本不以 ``CDK-`` 开头时返回 None。
    """
    normalized = "".join(raw_text.split()).upper()
    if not normalized.startswith(CDK_PREFIX):
        return None
    code = normalized[len(CDK_PREFIX) :].replace("-", "")
    if not CDK_CODE_PATTERN.fullmatch(code):
        return REPLY_FORMAT_ERROR
    return redeem_cdk(openid, code)


def redeem_cdk(openid: str, code: str) -> str:
    """校验当前码并为普通用户升级为高级用户。

    参数:
        openid: 发送兑换请求的微信用户 openid。
        code: 去除前缀和分组连字符后的 16 位兑换码。
    返回:
        对应兑换结果的中文回复文案。
    """
    try:
        with SessionLocal() as session:
            user = session.scalar(select(User).where(User.openid == openid))
            if user is None:
                return REPLY_USER_NOT_FOUND
            if user.user_level >= UserLevel.ADMIN:
                return REPLY_ALREADY_ADMIN
            if user.user_level >= UserLevel.PREMIUM:
                return REPLY_ALREADY_PREMIUM
            user_id = user.id
    except SQLAlchemyError:
        logger.exception("CDK 兑换查询用户失败")
        return REPLY_SYSTEM_BUSY

    with _state_lock:
        now = int(time())
        if code != _state.code:
            return REPLY_INVALID
        if now >= _state.expire_time:
            return REPLY_EXPIRED
        if user_id in _state.redeemed_user_ids:
            return REPLY_ALREADY_REDEEMED
        try:
            with SessionLocal.begin() as session:
                user = session.get(User, user_id)
                if user is None:
                    return REPLY_USER_NOT_FOUND
                if user.user_level >= UserLevel.ADMIN:
                    return REPLY_ALREADY_ADMIN
                if user.user_level >= UserLevel.PREMIUM:
                    return REPLY_ALREADY_PREMIUM
                # 按设计要求只修改 user_level，不刷新 updated_time。
                user.user_level = int(UserLevel.PREMIUM)
        except SQLAlchemyError:
            logger.exception("CDK 兑换更新用户等级失败")
            return REPLY_SYSTEM_BUSY
        _state.redeemed_user_ids.add(user_id)

    logger.info("CDK 兑换成功: user_id=%s", user_id)
    return REPLY_REDEEM_SUCCESS


async def run_cdk_rotation_scheduler() -> None:
    """常驻维护 CDK，在当前码过期时自动生成新码。

    参数:
        无。
    返回:
        无返回值；协程持续运行直至被取消，单次异常只记录日志并延迟重试。
    """
    while True:
        delay = _seconds_until_expire()
        # 保留最小等待，避免临界时刻因取整或时钟抖动造成空转。
        await asyncio.sleep(max(delay, CDK_MIN_ROTATION_DELAY_SECONDS))
        try:
            get_cdk_snapshot()
        except Exception:
            logger.exception("CDK 自动换码失败")
            await asyncio.sleep(CDK_RETRY_DELAY_SECONDS)
