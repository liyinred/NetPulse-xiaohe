"""即时 IP 按需探测的用户与 Agent 路由。"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.models.user import User
from app.schemas.on_demand_probe import (
    CreateProbeQueryRequest,
    CreateProbeQueryResponse,
    OnDemandAcceptedResponse,
    OnDemandResultRequest,
    OnDemandTaskResponse,
    ProbeQueryResultResponse,
)
from app.services.auth import get_current_user
from app.services.network import IPLookupError
from app.services.on_demand_probe import (
    claim_on_demand_task,
    create_probe_query,
    get_probe_query_result,
    save_on_demand_result,
)


router = APIRouter(prefix="/probes/on-demand", tags=["即时 IP 探测 Agent"])
web_router = APIRouter(prefix="/api/on-demand-probes", tags=["即时 IP 探测"])


@web_router.post("", response_model=CreateProbeQueryResponse)
async def create_user_probe_query(
    request: CreateProbeQueryRequest,
    user: Annotated[User, Depends(get_current_user)],
) -> CreateProbeQueryResponse:
    """创建当前用户的即时公网 IP 探测查询。

    参数:
        request: 用户输入的单个 IPv4 或 IPv6 地址。
        user: JWT 认证依赖解析出的当前用户。
    返回:
        独立查询标识、共享执行标识和初始状态。
    """
    try:
        data = await create_probe_query(user.id, request.target_ip)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except IPLookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return CreateProbeQueryResponse(data=data)


@web_router.get("/{query_id}", response_model=ProbeQueryResultResponse)
def get_user_probe_query(
    query_id: int,
    user: Annotated[User, Depends(get_current_user)],
) -> ProbeQueryResultResponse:
    """查询当前用户拥有的即时 IP 探测进度和结果。

    参数:
        query_id: 用户查询记录主键。
        user: JWT 认证依赖解析出的当前用户。
    返回:
        节点进度计数及异网、跨省结果列表。
    """
    try:
        data = get_probe_query_result(user.id, query_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return ProbeQueryResultResponse(data=data)


@router.get("/tasks", response_model=OnDemandTaskResponse)
async def poll_on_demand_task(
    device_id: str = Query(min_length=1, max_length=64),
) -> OnDemandTaskResponse:
    """长轮询并为 Agent 领取一个按需探测任务。

    参数:
        device_id: Agent 本地设备标识。
    返回:
        八秒内领取到的任务；无任务时返回空 data。
    """
    try:
        for attempt in range(9):
            task = await run_in_threadpool(claim_on_demand_task, device_id)
            if task is not None:
                return OnDemandTaskResponse(data=task)
            if attempt < 8:
                await asyncio.sleep(1)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return OnDemandTaskResponse()


@router.post("/results", response_model=OnDemandAcceptedResponse)
def receive_on_demand_result(
    request: OnDemandResultRequest,
) -> OnDemandAcceptedResponse:
    """接收并幂等保存 Agent 的三协议按需探测结果。

    参数:
        request: 节点任务及其完整 ICMP、TCP、UDP 汇总结果。
    返回:
        中央服务接受成功标志。
    """
    try:
        save_on_demand_result(request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return OnDemandAcceptedResponse()
