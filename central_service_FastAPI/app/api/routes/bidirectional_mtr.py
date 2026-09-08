"""双向 MTR 的用户与 Agent 路由。"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from app.models.user import User
from app.schemas.bidirectional_mtr import CreateMTRRequest, CreateMTRResponse, MTRAcceptedResponse, MTRAgentTaskResponse, MTRDeviceListResponse, MTRResultRequest, MTRTaskResultResponse
from app.services.auth import get_current_user
from app.services.mtr_metadata import enrich_mtr_result
from app.services.bidirectional_mtr import claim_mtr_task, create_mtr_task, get_mtr_result, list_mtr_devices, save_mtr_result


router = APIRouter(prefix="/probes/mtr", tags=["双向 MTR Agent"])
web_router = APIRouter(prefix="/api/bidirectional-mtr", tags=["双向 MTR"])


@web_router.get("/devices", response_model=MTRDeviceListResponse)
def get_available_devices(user: Annotated[User, Depends(get_current_user)]) -> MTRDeviceListResponse:
    """获取当前用户可用于双向 MTR 的在线设备。

    参数:
        user: JWT 认证依赖解析出的当前用户。
    返回:
        设备与其有效公开公网 IP 列表。
    """
    return MTRDeviceListResponse(data=list_mtr_devices(user.id))


@web_router.post("", response_model=CreateMTRResponse)
def create_user_mtr_task(request: CreateMTRRequest, user: Annotated[User, Depends(get_current_user)]) -> CreateMTRResponse:
    """创建当前用户选择设备间的双向 MTR 任务。

    参数:
        request: 两台设备和两个公网 IP 的选择。
        user: JWT 认证依赖解析出的当前用户。
    返回:
        新建主任务标识与初始状态。
    """
    try:
        data = create_mtr_task(user.id, request.sourceDeviceId, request.sourceIpId, request.targetDeviceId, request.targetIpId)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CreateMTRResponse(data=data)


@web_router.get("/{task_id}", response_model=MTRTaskResultResponse)
async def get_user_mtr_task(task_id: int, user: Annotated[User, Depends(get_current_user)]) -> MTRTaskResultResponse:
    """查询当前用户双向 MTR 主任务的结果。

    参数:
        task_id: 双向 MTR 主任务主键。
        user: JWT 认证依赖解析出的当前用户。
    返回:
        两个方向的状态、逐跳路径和归属信息。
    """
    try:
        data = await run_in_threadpool(get_mtr_result, user.id, task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    await enrich_mtr_result(data)
    return MTRTaskResultResponse(data=data)


@router.get("/tasks", response_model=MTRAgentTaskResponse)
async def poll_mtr_task(device_id: str = Query(min_length=1, max_length=64)) -> MTRAgentTaskResponse:
    """长轮询并为 Agent 领取一个单方向双向 MTR 任务。

    参数:
        device_id: Agent 本地设备标识。
    返回:
        八秒内领取到的任务；无任务时返回空 data。
    """
    try:
        for attempt in range(9):
            task = await run_in_threadpool(claim_mtr_task, device_id)
            if task is not None:
                return MTRAgentTaskResponse(data=task)
            if attempt < 8:
                await asyncio.sleep(1)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return MTRAgentTaskResponse()


@router.post("/results", response_model=MTRAcceptedResponse)
def receive_mtr_result(request: MTRResultRequest) -> MTRAcceptedResponse:
    """接收并幂等保存 Agent 的单方向 MTR 进度或最终结果。

    参数:
        request: 包含方向租约、地址快照、逐跳统计和结束标志的上报内容。
    返回:
        中央服务接受成功标志。
    """
    try:
        save_mtr_result(request)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return MTRAcceptedResponse()
