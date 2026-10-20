"""CDK 兑换码 API 数据模型。"""

from pydantic import BaseModel


class CdkCurrentData(BaseModel):
    """当前 CDK 的展示数据。"""

    code: str
    createdTime: int
    expireTime: int
    serverTime: int
    expireSeconds: int


class CdkCurrentResponse(BaseModel):
    """获取当前 CDK 的统一响应。"""

    code: int = 200
    msg: str = "CDK 获取成功"
    data: CdkCurrentData
