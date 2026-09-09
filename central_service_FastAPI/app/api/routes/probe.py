"""持续探测目标、结果和告警路由。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.models.user import User
from app.schemas.probe import (
    ProbeAcceptedResponse,
    ProbeAlertsRequest,
    ProbeNodesResponse,
    ProbeRangeType,
    ProbeReportResponse,
    ProbeResultRequest,
    ProbeTargetsRequest,
    ProbeTargetsResponse,
    ProbeTrendResponse,
    ProtocolType,
)
from app.services.auth import get_current_user
from app.services.network import IPLookupError
from app.services.wechat import send_template_messages
from app.services.probe import (
    discover_probe_targets,
    get_user_probe_report,
    get_user_probe_trend,
    list_user_probe_nodes,
    save_probe_result,
)


router = APIRouter(prefix="/probes", tags=["持续探测"])
web_router = APIRouter(prefix="/api/probes", tags=["探测趋势"])


@web_router.get("/nodes", response_model=ProbeNodesResponse)
def get_probe_nodes(
    user: Annotated[User, Depends(get_current_user)],
) -> ProbeNodesResponse:
    """按用户等级查询可访问且已有结果的探测源节点。

    参数:
        user: JWT 认证依赖解析出的当前用户。
    返回:
        统一响应包装的探测节点列表。
    """
    return ProbeNodesResponse(data=list_user_probe_nodes(user.id, user.user_level))


@web_router.get("/trend", response_model=ProbeTrendResponse)
def get_probe_trend(
    user: Annotated[User, Depends(get_current_user)],
    source_ip_id: int = Query(alias="sourceIpId", ge=1),
    probe_mode: int = Query(alias="probeMode", ge=1, le=2),
    protocol_type: ProtocolType = Query(alias="protocolType"),
    range_type: ProbeRangeType = Query(alias="rangeType"),
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
) -> ProbeTrendResponse:
    """查询当前用户指定节点和探测模式的分钟趋势。

    参数:
        user: JWT 认证依赖解析出的当前用户。
        source_ip_id: 用户选择的源 IP 记录主键。
        probe_mode: 探测模式编码，1 为异网，2 为跨省。
        protocol_type: icmp、tcp 或 udp 协议类型。
        range_type: 最近 1、2、7 天或月份范围。
        month: 月份范围使用的 YYYY-MM 字符串。
    返回:
        统一响应包装的分钟趋势数据。
    """
    try:
        data = get_user_probe_trend(
            user.id,
            user.user_level,
            source_ip_id,
            probe_mode,
            protocol_type,
            range_type,
            month,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProbeTrendResponse(data=data)


@web_router.get("/report", response_model=ProbeReportResponse)
def get_probe_report(
    user: Annotated[User, Depends(get_current_user)],
    source_ip_id: int = Query(alias="sourceIpId", ge=1),
    probe_mode: int = Query(alias="probeMode", ge=1, le=2),
    range_type: ProbeRangeType = Query(alias="rangeType"),
    month: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
) -> ProbeReportResponse:
    """查询当前用户指定节点和探测模式的概览报告。

    参数:
        user: JWT 认证依赖解析出的当前用户。
        source_ip_id: 用户选择的源 IP 记录主键。
        probe_mode: 探测模式编码，1 为异网，2 为跨省。
        range_type: 最近 1、2、7 天或月份范围。
        month: 月份范围使用的 YYYY-MM 字符串。
    返回:
        统一响应包装的三协议概览报告。
    """
    try:
        data = get_user_probe_report(
            user.id,
            user.user_level,
            source_ip_id,
            probe_mode,
            range_type,
            month,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ProbeReportResponse(data=data)


@router.post(
    "/targets",
    response_model=ProbeTargetsResponse,
    response_model_exclude_none=True,
)
async def get_probe_targets(
    request: ProbeTargetsRequest,
) -> ProbeTargetsResponse:
    """刷新设备源地址并查询异网、跨省探测目标。

    参数:
        request: 设备标识和当前公网源地址。
    返回:
        按 IP 版本和探测分类拆分的目标列表。
    """
    try:
        return await discover_probe_targets(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IPLookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/results", response_model=ProbeAcceptedResponse)
async def receive_probe_result(
    request: ProbeResultRequest,
) -> ProbeAcceptedResponse:
    """保存分钟结果、推进告警状态，并在事务提交后发送通知。

    参数:
        request: 一个分类、IP 版本和源地址的完整窗口结果。
    返回:
        接收成功标志；通知失败时传播微信服务异常。
    """
    try:
        messages = await run_in_threadpool(save_probe_result, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await send_template_messages(messages)
    return ProbeAcceptedResponse()


@router.post("/alerts", response_model=ProbeAcceptedResponse)
async def receive_probe_alerts(
    request: ProbeAlertsRequest,
) -> ProbeAcceptedResponse:
    """兼容旧 Agent 的分钟告警请求，仅确认接收，不入库或通知。

    参数:
        request: Agent 生成的自然分钟聚合丢包告警。
    返回:
        接收成功标志。
    """
    return ProbeAcceptedResponse()
