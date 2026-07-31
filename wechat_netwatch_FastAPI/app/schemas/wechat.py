"""微信 API 数据模型。"""

from pydantic import BaseModel


class QRCodeResponse(BaseModel):
    """带参数二维码创建结果。"""

    scene_str: str
    ticket: str
    expire_seconds: int
    url: str
    image_url: str
