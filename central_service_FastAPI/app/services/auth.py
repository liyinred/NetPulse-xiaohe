"""JWT 网页认证服务。"""

from datetime import datetime, timedelta, timezone
from time import time
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy import select

from app.core.config import JWT_EXPIRE_MINUTES, JWT_SECRET_KEY
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.user import UserLevel
from app.services.device import find_scene_user_id


JWT_ALGORITHM = "HS256"
JWT_ISSUER = "netpulse-central-service"
bearer_scheme = HTTPBearer(auto_error=False)
USER_LEVEL_ROLES = {
    UserLevel.ADMIN: "R_ADMIN",
    UserLevel.PREMIUM: "R_PREMIUM",
}
DEFAULT_USER_ROLE = "R_USER"


def create_access_token(user_id: int) -> str:
    """为微信用户签发 JWT access token。

    参数:
        user_id: users 表内部主键。
    返回:
        已签名且包含过期时间的 JWT 字符串。
    """
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=JWT_EXPIRE_MINUTES)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": "access",
            "iat": issued_at,
            "exp": expires_at,
            "iss": JWT_ISSUER,
        },
        JWT_SECRET_KEY,
        algorithm=JWT_ALGORITHM,
    )


def find_login_user(scene_str: str) -> User | None:
    """查询有效场景值对应的已关注微信用户。

    参数:
        scene_str: 微信二维码携带的场景值。
    返回:
        扫码成功时返回用户，否则返回 None。
    """
    with SessionLocal() as session:
        user_id = find_scene_user_id(session, scene_str, int(time()))
        if user_id is None:
            return None
        return session.scalar(select(User).where(User.id == user_id))


def decode_access_token(token: str) -> int:
    """校验 JWT 并提取用户主键。

    参数:
        token: 客户端提交的 JWT access token。
    返回:
        token subject 中的用户主键。
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET_KEY,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
        )
        if payload.get("type") != "access":
            raise InvalidTokenError("JWT 类型无效")
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="登录凭据无效或已过期") from exc
    return user_id


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    """从 Authorization Bearer token 获取当前用户。

    参数:
        credentials: FastAPI 解析的 Bearer 认证凭据。
    返回:
        当前有效且仍关注服务号的用户。
    """
    if credentials is None:
        raise HTTPException(status_code=401, detail="缺少登录凭据")
    user_id = decode_access_token(credentials.credentials)
    with SessionLocal() as session:
        user = session.scalar(
            select(User).where(
                User.id == user_id,
                User.subscribe_status == 1,
            )
        )
        if user is None:
            raise HTTPException(status_code=401, detail="登录用户不存在或已取消关注")
        session.expunge(user)
        return user


def get_user_roles(user_level: int) -> list[str]:
    """按用户等级生成前端路由守卫使用的角色列表。

    参数:
        user_level: users 表中的用户等级。
    返回:
        对应的前端角色标识列表。
    """
    return [USER_LEVEL_ROLES.get(user_level, DEFAULT_USER_ROLE)]


def require_min_user_level(user: User, min_level: UserLevel, detail: str) -> User:
    """校验用户等级不低于指定等级。

    参数:
        user: 已认证的当前用户。
        min_level: 允许访问的最低用户等级。
        detail: 权限不足时返回的 403 错误信息。
    返回:
        通过等级校验的当前用户。
    """
    if user.user_level < min_level:
        raise HTTPException(status_code=403, detail=detail)
    return user


def get_current_admin(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """校验当前网页用户是否为管理员。

    参数:
        user: JWT 认证依赖解析出的当前用户。
    返回:
        用户等级为 9 的管理员用户。
    """
    return require_min_user_level(user, UserLevel.ADMIN, "仅管理员可使用此功能")


def get_current_premium_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    """校验当前网页用户是否为高级用户或管理员。

    参数:
        user: JWT 认证依赖解析出的当前用户。
    返回:
        用户等级不低于高级用户的当前用户。
    """
    return require_min_user_level(user, UserLevel.PREMIUM, "仅高级用户和管理员可使用此功能")
