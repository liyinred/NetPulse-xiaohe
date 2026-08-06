"""持续探测目标、结果和告警路由。"""

from fastapi import APIRouter, HTTPException

from app.schemas.probe import (
    ProbeAcceptedResponse,
    ProbeAlertsRequest,
    ProbeResultRequest,
    ProbeTargetsRequest,
    ProbeTargetsResponse,
)
from app.services.network import IPLookupError
from app.services.probe import (
    discover_probe_targets,
    save_probe_alerts,
    save_probe_result,
)


router = APIRouter(prefix="/probes", tags=["持续探测"])


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
    """接收并持久化自然分钟探测结果。

    参数:
        request: 一个分类、IP 版本和源地址的完整窗口结果。
    返回:
        接收成功标志。
    """
    try:
        save_probe_result(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProbeAcceptedResponse()


@router.post("/alerts", response_model=ProbeAcceptedResponse)
async def receive_probe_alerts(
    request: ProbeAlertsRequest,
) -> ProbeAcceptedResponse:
    """接收并持久化自然分钟聚合丢包告警。

    参数:
        request: Agent 生成的自然分钟聚合丢包告警。
    返回:
        接收成功标志。
    """
    try:
        await save_probe_alerts(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProbeAcceptedResponse()
