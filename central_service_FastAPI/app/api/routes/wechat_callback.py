import base64
import binascii
import hashlib
import hmac
import logging
import struct
from time import time
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import WECHAT_APP_ID, WECHAT_ENCODING_AES_KEY, WECHAT_TOKEN
from app.db.session import SessionLocal
from app.models.user import User
from app.services.cdk import handle_cdk_text

MAX_REQUEST_BODY_BYTES = 1024 * 1024
QR_SCENE_PREFIX = "qrscene_"
MAX_OPENID_LENGTH = 128
MAX_SCENE_STR_LENGTH = 16
SUBSCRIPTION_STATUS_BY_EVENT = {
    "subscribe": 1,
    "unsubscribe": 0,
    "scan": 1,
}

logger = logging.getLogger(__name__)
router = APIRouter()


def load_aes_key(encoding_aes_key: str) -> bytes:
    """解析微信 EncodingAESKey。

    参数:
        encoding_aes_key: 微信后台配置的 43 字符 EncodingAESKey。
    返回:
        Base64 解码后的 32 字节 AES key。
    """
    try:
        aes_key = base64.b64decode(encoding_aes_key + "=", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise RuntimeError("WECHAT_ENCODING_AES_KEY 不是有效的 Base64 内容") from exc
    if len(aes_key) != 32:
        raise RuntimeError("WECHAT_ENCODING_AES_KEY 解码后必须为 32 字节")
    return aes_key


AES_KEY = load_aes_key(WECHAT_ENCODING_AES_KEY)


def calculate_signature(*parts: str) -> str:
    """计算微信要求的 SHA-1 签名。

    参数:
        parts: Token、timestamp、nonce 以及可选 Encrypt 等签名字段。
    返回:
        字典序排序并拼接后的 SHA-1 十六进制摘要。
    """
    payload = "".join(sorted(parts)).encode("utf-8")
    return hashlib.sha1(payload).hexdigest()


def verify_signature(signature: str, *parts: str) -> bool:
    """以恒定时间比较方式校验微信签名。

    参数:
        signature: 微信请求携带的 signature 或 msg_signature。
        parts: 参与签名的 Token、timestamp、nonce 和可选 Encrypt。
    返回:
        签名一致时返回 True，否则返回 False。
    """
    expected = calculate_signature(*parts)
    return hmac.compare_digest(expected, signature)


def remove_pkcs7_padding(data: bytes) -> bytes:
    """移除微信 AES 消息使用的 PKCS#7 padding。

    参数:
        data: AES 解密后的带 padding 字节串。
    返回:
        移除 padding 后的原始字节串。
    """
    if not data:
        raise ValueError("解密结果为空")
    padding_size = data[-1]
    if padding_size < 1 or padding_size > 32:
        raise ValueError("PKCS#7 padding 长度无效")
    if data[-padding_size:] != bytes([padding_size]) * padding_size:
        raise ValueError("PKCS#7 padding 内容无效")
    return data[:-padding_size]


def decrypt_message(encrypted: str) -> tuple[str, str]:
    """解密微信安全模式消息并提取 AppID。

    参数:
        encrypted: XML Encrypt 节点或加密 echostr 的 Base64 文本。
    返回:
        包含消息明文和消息尾部 AppID 的元组。
    """
    try:
        encrypted_bytes = base64.b64decode(encrypted, validate=True)
        if not encrypted_bytes or len(encrypted_bytes) % 16 != 0:
            raise ValueError("AES 密文长度无效")
        decryptor = Cipher(
            algorithms.AES(AES_KEY), modes.CBC(AES_KEY[:16])
        ).decryptor()
        full_message = remove_pkcs7_padding(
            decryptor.update(encrypted_bytes) + decryptor.finalize()
        )
        if len(full_message) < 20:
            raise ValueError("解密消息长度不足")
        message_length = struct.unpack(">I", full_message[16:20])[0]
        message_end = 20 + message_length
        if message_end > len(full_message):
            raise ValueError("消息长度字段超出解密内容")
        message = full_message[20:message_end].decode("utf-8")
        app_id = full_message[message_end:].decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError, struct.error) as exc:
        raise ValueError("微信消息解密失败") from exc
    return message, app_id


def _cdata(value: str) -> str:
    """将文本包装为可安全嵌入 XML 的 CDATA 片段。

    参数:
        value: 待包装的文本。
    返回:
        转义了 CDATA 结束符的 CDATA 字符串。
    """
    return "<![CDATA[" + value.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def build_text_reply_xml(message: dict[str, str], content: str) -> str:
    """构造微信被动回复的文本消息 XML。

    参数:
        message: 解析后的微信请求 XML 一级字段。
        content: 回复正文。
    返回:
        可直接返回给微信的明文 XML。
    """
    return (
        "<xml>"
        f"<ToUserName>{_cdata(message.get('FromUserName', ''))}</ToUserName>"
        f"<FromUserName>{_cdata(message.get('ToUserName', ''))}</FromUserName>"
        f"<CreateTime>{int(time())}</CreateTime>"
        "<MsgType><![CDATA[text]]></MsgType>"
        f"<Content>{_cdata(content)}</Content>"
        "</xml>"
    )


def parse_xml(xml_text: str) -> dict[str, str]:
    """解析微信推送的扁平 XML 消息。

    参数:
        xml_text: 微信请求体或解密后的 XML 文本。
    返回:
        XML 一级节点名与文本值组成的字典。
    """
    upper_text = xml_text.upper()
    if "<!DOCTYPE" in upper_text or "<!ENTITY" in upper_text:
        raise ValueError("XML 不允许包含 DTD 或 ENTITY")
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError("XML 格式无效") from exc
    if root.tag != "xml":
        raise ValueError("XML 根节点必须为 xml")
    return {child.tag: child.text or "" for child in root}


async def read_limited_body(request: Request) -> bytes:
    """读取请求体并限制最大字节数。

    参数:
        request: FastAPI 原始请求。
    返回:
        完整请求体字节串。
    """
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_REQUEST_BODY_BYTES:
                raise HTTPException(status_code=413, detail="请求体过大")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Content-Length 无效") from exc

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_REQUEST_BODY_BYTES:
            raise HTTPException(status_code=413, detail="请求体过大")
        body.extend(chunk)
    return bytes(body)


def validate_app_id(message_app_id: str) -> None:
    """在已配置 AppID 时校验解密消息中的 AppID。

    参数:
        message_app_id: 微信加密消息尾部携带的服务号 AppID。
    返回:
        校验成功或未配置 WECHAT_APP_ID 时无返回值。
    """
    if WECHAT_APP_ID and not hmac.compare_digest(WECHAT_APP_ID, message_app_id):
        raise HTTPException(status_code=403, detail="AppID 校验失败")


def extract_scene_str(event_key: str | None) -> str | None:
    """从微信事件的 EventKey 中提取二维码场景值。

    参数:
        event_key: 微信事件携带的 EventKey；新关注扫码事件带 qrscene_ 前缀。
    返回:
        去除 qrscene_ 前缀后的 scene_str；字段为空时返回 None。
    """
    if not event_key:
        return None
    scene_str = event_key.removeprefix(QR_SCENE_PREFIX)
    if not scene_str or len(scene_str) > MAX_SCENE_STR_LENGTH:
        raise ValueError("EventKey 中的 scene_str 无效")
    return scene_str


def update_subscription_user(session: Session, message: dict[str, str]) -> bool:
    """根据关注、取消关注或扫码事件新增或更新微信用户。

    参数:
        session: 当前 SQLAlchemy 数据库会话。
        message: 解析后的微信 XML 一级字段。
    返回:
        已处理目标事件时返回 True，非目标事件返回 False。
    """
    if message.get("MsgType", "").lower() != "event":
        return False

    event = message.get("Event", "").lower()
    subscribe_status = SUBSCRIPTION_STATUS_BY_EVENT.get(event)
    if subscribe_status is None:
        return False

    openid = message.get("FromUserName", "").strip()
    if not openid or len(openid) > MAX_OPENID_LENGTH:
        raise ValueError("关注状态事件缺少有效的 FromUserName")

    scene_str = extract_scene_str(message.get("EventKey"))
    current_time = int(time())
    user = session.scalar(select(User).where(User.openid == openid))
    pending_user = None
    if scene_str is not None:
        pending_user = session.scalar(
            select(User).where(User.scene_str == scene_str)
        )
    if user is None:
        if pending_user is not None:
            user = pending_user
            user.openid = openid
        else:
            user = User(
                openid=openid,
                scene_str=scene_str,
                created_time=current_time,
            )
            session.add(user)
    elif pending_user is not None and pending_user.id != user.id:
        session.delete(pending_user)
        session.flush()

    user.subscribe_status = subscribe_status
    if scene_str is not None:
        user.scene_str = scene_str
    user.updated_time = current_time
    return True


def handle_message(message: dict[str, str]) -> str | None:
    """处理已验签的微信消息或事件。

    参数:
        message: 解析后的微信 XML 一级字段。
    返回:
        文本消息需要被动回复的文案；事件或无需回复时返回 None。
    """
    logger.info(
        "收到微信推送: msg_type=%s event=%s from_user=%s",
        message.get("MsgType", ""),
        message.get("Event", ""),
        message.get("FromUserName", ""),
    )
    if (
        message.get("MsgType", "").lower() == "event"
        and message.get("Event", "").lower() in SUBSCRIPTION_STATUS_BY_EVENT
    ):
        with SessionLocal.begin() as session:
            update_subscription_user(session, message)
        return None

    if message.get("MsgType", "").lower() != "text":
        return None

    openid = message.get("FromUserName", "").strip()
    if not openid or len(openid) > MAX_OPENID_LENGTH:
        logger.warning("文本消息缺少有效的 FromUserName")
        return None
    return handle_cdk_text(message.get("Content", ""), openid)


@router.get("/wechat/callback", response_class=PlainTextResponse)
async def verify_url(
    timestamp: str = Query(...),
    nonce: str = Query(...),
    echostr: str = Query(...),
    signature: str | None = Query(None),
    msg_signature: str | None = Query(None),
) -> PlainTextResponse:
    """处理微信服务器配置的 GET URL 验证请求。

    参数:
        timestamp: 微信请求时间戳。
        nonce: 微信请求随机数。
        echostr: 明文随机串或安全模式加密随机串。
        signature: 明文模式签名。
        msg_signature: 安全模式消息签名。
    返回:
        验签成功后的原始明文 echostr。
    """
    if msg_signature:
        if not verify_signature(
            msg_signature, WECHAT_TOKEN, timestamp, nonce, echostr
        ):
            raise HTTPException(status_code=403, detail="msg_signature 校验失败")
        try:
            decrypted_echo, message_app_id = decrypt_message(echostr)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        validate_app_id(message_app_id)
        return PlainTextResponse(decrypted_echo)

    if not signature or not verify_signature(
        signature, WECHAT_TOKEN, timestamp, nonce
    ):
        raise HTTPException(status_code=403, detail="signature 校验失败")
    return PlainTextResponse(echostr)


@router.post("/wechat/callback", response_class=PlainTextResponse)
async def receive_message(
    request: Request,
    timestamp: str = Query(...),
    nonce: str = Query(...),
    signature: str | None = Query(None),
    msg_signature: str | None = Query(None),
) -> Response:
    """接收、验签并处理微信 XML 消息或事件推送。

    参数:
        request: FastAPI 原始请求，用于读取 XML body。
        timestamp: 微信请求时间戳。
        nonce: 微信请求随机数。
        signature: 明文模式签名。
        msg_signature: 兼容或安全模式消息签名。
    返回:
        无需回复时返回微信认可的 success 文本，否则返回文本消息的被动回复 XML。
    """
    try:
        body_text = (await read_limited_body(request)).decode("utf-8")
        outer_message = parse_xml(body_text)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    encrypted = outer_message.get("Encrypt")
    if encrypted and not msg_signature:
        raise HTTPException(status_code=403, detail="缺少 msg_signature")
    if encrypted:
        if not verify_signature(
            msg_signature, WECHAT_TOKEN, timestamp, nonce, encrypted
        ):
            raise HTTPException(status_code=403, detail="msg_signature 校验失败")
        try:
            decrypted_xml, message_app_id = decrypt_message(encrypted)
            message = parse_xml(decrypted_xml)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        validate_app_id(message_app_id)
    else:
        if not signature or not verify_signature(
            signature, WECHAT_TOKEN, timestamp, nonce
        ):
            raise HTTPException(status_code=403, detail="signature 校验失败")
        message = outer_message

    try:
        reply_text = handle_message(message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if reply_text is None:
        return PlainTextResponse("success")

    reply_xml = build_text_reply_xml(message, reply_text)
    return Response(content=reply_xml, media_type="application/xml; charset=utf-8")
