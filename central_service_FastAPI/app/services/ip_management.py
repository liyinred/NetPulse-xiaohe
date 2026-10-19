"""IP 管理查询服务。"""

from ipaddress import IPv4Address, IPv6Address
from time import time

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.ip_dict import IPDict
from app.schemas.ip_management import IPListItem
from app.schemas.pagination import PaginatedData, PaginationParams
from app.services.network import (
    ISP_NAMES,
    PROVINCE_NAMES,
    lookup_network,
)
from app.services.pagination import paginate_query


IP_SORT_COLUMNS = {
    "ip": IPDict.ip,
    "ipVersion": IPDict.ip_version,
    "publicStatus": IPDict.public_status,
    "isp": IPDict.isp,
    "province": IPDict.province,
    "city": IPDict.city,
    "updateTime": IPDict.update_time,
}


def _build_ip_list_item(record: IPDict) -> IPListItem:
    """将 IPDict ORM 记录转换为管理列表项。

    参数:
        record: 要转换的 IPDict ORM 记录。
    返回:
        包含编码及展示名称的 IP 管理列表项。
    """
    return IPListItem(
        id=record.id,
        ip=record.ip,
        ipVersion=record.ip_version,
        publicStatus=record.public_status,
        isp=record.isp,
        ispName=ISP_NAMES.get(record.isp, "未知"),
        province=record.province,
        provinceName=PROVINCE_NAMES.get(record.province, "未知"),
        city=record.city,
        updateTime=record.update_time,
    )


def list_ips(
    pagination: PaginationParams,
    ip: str | None = None,
    ip_version: int | None = None,
    isp: int | None = None,
    province: int | None = None,
    city: str | None = None,
    public_status: int | None = None,
) -> PaginatedData[IPListItem]:
    """按筛选条件查询 ip_dict 表并返回数据库分页结果。

    参数:
        pagination: 统一分页和排序参数。
        ip: IP 地址模糊筛选值。
        ip_version: IP 版本精确筛选值。
        isp: 运营商编码精确筛选值。
        province: 省份编码精确筛选值。
        city: 城市名称模糊筛选值。
        public_status: 公开状态精确筛选值。
    返回:
        IP 列表记录、当前页、每页条数和总记录数。
    """
    statement = select(IPDict)
    if ip:
        statement = statement.where(IPDict.ip.contains(ip))
    if ip_version is not None:
        statement = statement.where(IPDict.ip_version == ip_version)
    if isp is not None:
        statement = statement.where(IPDict.isp == isp)
    if province is not None:
        statement = statement.where(IPDict.province == province)
    if city:
        statement = statement.where(IPDict.city.contains(city))
    if public_status is not None:
        statement = statement.where(IPDict.public_status == public_status)

    with SessionLocal() as session:
        ip_records, total = paginate_query(
            session,
            statement,
            pagination,
            IP_SORT_COLUMNS,
            "updateTime",
            IPDict.id,
        )
        records = [_build_ip_list_item(record) for record in ip_records]
    return PaginatedData(
        records=records,
        current=pagination.current,
        size=pagination.size,
        total=total,
    )


async def upsert_ip_record(
    public_ip: IPv4Address | IPv6Address,
    public_status: int,
) -> IPListItem:
    """查询 IP 归属信息并新增或刷新 ip_dict 记录。

    参数:
        public_ip: 已校验并规范化的 IPv4 或 IPv6 地址。
        public_status: 要保存的公开状态，0 为未公开，1 为公开。
    返回:
        新增或刷新后的 IP 管理列表项。
    """
    network_info = await lookup_network(public_ip)
    current_time = int(time())
    ip_text = str(public_ip)

    with SessionLocal.begin() as session:
        record = session.scalar(select(IPDict).where(IPDict.ip == ip_text))
        if record is None:
            record = IPDict(
                ip=ip_text,
                ip_version=public_ip.version,
                isp=network_info.isp,
                province=network_info.province,
                city=network_info.city_name,
                public_status=public_status,
                update_time=current_time,
            )
            session.add(record)
        else:
            record.ip_version = public_ip.version
            record.public_status = public_status
            record.isp = network_info.isp
            record.province = network_info.province
            record.city = network_info.city_name
            record.update_time = current_time

        session.flush()
        return _build_ip_list_item(record)


def update_ip_public_status(
    ip_id: int,
    public_status: int,
) -> IPListItem | None:
    """按记录 ID 修改 IP 公开状态。

    参数:
        ip_id: ip_dict 表记录 ID。
        public_status: 新公开状态，0 为未公开，1 为公开。
    返回:
        更新后的 IP 管理列表项；记录不存在时返回 None。
    """
    with SessionLocal.begin() as session:
        record = session.get(IPDict, ip_id)
        if record is None:
            return None
        record.public_status = public_status
        record.update_time = int(time())
        session.flush()
        return _build_ip_list_item(record)
