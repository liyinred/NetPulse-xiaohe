# 微信服务号网络质量探测系统设计文档

## 1. 项目概述

| 项目     | 内容                           |
| -------- | ------------------------------ |
| 文档版本 | v0.08                          |
| 更新日期 | 2026-08-04                     |
| 技术栈   | Golang Agent、FastAPI 中央服务 |
| 运行平台 | Linux                          |

本项目用于在用户自有 Linux 服务器上持续探测异网和跨省网络质量。设备绑定成功后，Agent 无需用户选择探测类型，也无需用户手动输入目标 IP；Agent 自动向中央服务查询当前设备对应的异网与跨省目标 IP 列表，在相同 IP 版本内对两个分类列表按 IP 去重合并，并在单个 Go 进程内对合并后的目标执行 ICMP、TCP 和 UDP 探测。IPv4 源地址只探测 IPv4 目标，IPv6 源地址只探测 IPv6 目标；同一 IP 同时属于异网和跨省时只执行一次实际网络探测。每个整分钟窗口结束时，Agent 按 `device_id + probe_mode + ip_version + source_ip` 分组上报三种协议的探测结果，各目标的 `target_ip` 和汇总结果保存在 `targets` 数组中；任一单次探测发生丢包时，Agent 额外上报告警事件。用户在微信服务号中选择接收异网告警、跨省告警或同时接收两类告警，中央服务按用户的告警类型设置发送通知。

### 1.1 项目目标

1. 通过微信服务号扫码完成用户与设备绑定。
2. 登录成功后由 Agent 自动查询当前设备按 IPv4/IPv6 分组的异网与跨省目标 IP 列表，不要求用户选择探测类型或输入目标 IP。
3. 对相同 IP 版本的异网和跨省列表按 IP 去重合并，并对合并后的每个唯一目标 IP 固定执行 ICMP、TCP 和 UDP 三种探测。
4. 每个整分钟窗口结束时，以 JSON 格式上报当前窗口的 Unix 时间戳、丢包率和平均延迟。
5. 任一单次探测发生丢包时上报告警事件，并按用户在微信服务号中设置的告警类型发送通知。
6. 以单个 Linux 二进制和 `systemd` 服务方式持久部署，探测过程不创建子进程。
7. 由中央服务一次查询并按探测分类和 IP 版本返回 ISP 不同或省份不同且处于公开状态的设备关联公网 IP。

## 2. 关键设计决策

### 2.1 两层架构

系统分为中央控制服务和 Linux Agent：

- **中央服务**：负责微信回调、二维码生成、绑定管理、设备管理、用户告警类型设置、探测结果与告警事件接收和微信通知。
- **Linux Agent**：负责终端交互、异网与跨省目标查询、ICMP、UDP、TCP 探测，以及绑定状态、分钟探测结果和丢包告警事件上报。

### 2.2 设备身份

- `device_id`：首次运行时随机生成 `UUID v4`，作为 Agent 使用的稳定设备标识。
- `openid`：仅由中央服务保存和使用，不返回给 Agent，也不写入本地配置。
- `device_related_id`：中央服务在公网地址获取和绑定过程中识别设备的 IPv4/IPv6，并通过 `ip_dict.device_related_id` 将 IP 记录关联到 `devices.id`；Agent 不在本地持久化该字段。
- `public_status`：存储在 `ip_dict` 中，控制该公网 IP 是否可被选为探测目标；`0` 表示未公开，`1` 表示公开。新 IP 默认值为 `1`，后续内部控制器关联的 IP 按 13.3 节设为 `0`。

中央服务通过 `devices.id = ip_dict.device_related_id` 维护设备与多个公网 IP 的一对多关联，Agent 和中央服务之间的设备识别只使用 `device_id`。后续增加基于 salt 的设备身份校验，具体方案见 13.2 节。

### 2.3 结果与告警上报

系统分别处理分钟探测结果和单次丢包告警。Agent 在每个整分钟窗口结束时，按 `device_id + probe_mode + ip_version + source_ip` 分组，将同一组内各 `target_ip` 的 ICMP、TCP 和 UDP 汇总结果放入 `targets` 数组后上报；任一单次探测发生丢包时，立即额外上报一条带有 `probe_mode`、`ip_version` 和 `source_ip` 的告警事件。`probe_mode` 仅表示目标所属的异网或跨省分类，不再表示用户在 Agent 中选择的运行模式。中央服务保存结果与事件，并根据告警事件中的 `device_id` 查询源设备所属用户的 `alert_type`；仅当该值包含对应告警类型时发送微信消息。

## 3. 总体架构

```mermaid
flowchart LR
    User["用户终端"] --> Agent["Linux Agent"]
    Agent -->|"绑定、心跳、目标查询、分钟结果与告警事件"| API["中央控制服务"]
    API -->|"按分类与 IP 版本分组的目标 IP 列表"| Agent
    Agent -->|"ICMP / UDP / TCP"| Target["目标 IPv4/IPv6 与端口"]
    API --> DB["远程数据库"]
    API --> Notify["微信通知模块"]
    Notify --> WeChat["微信公众平台"]
    WeChat -->|"关注 / 扫码事件 / 用户告警类型设置"| Callback["微信交互处理"]
    Callback --> API
```

### 3.1 中央服务模块

| 模块                 | 职责                                             |
| -------------------- | ------------------------------------------------ |
| WeChat Client        | 管理`access_token`、二维码、关注状态和模板消息 |
| Binding Service      | 创建绑定会话并处理扫码事件                       |
| Device Service       | 管理设备、设备与 IP 的一对多关系及设备心跳       |
| IP Dictionary        | 管理 IP、IP 版本、ISP、省份、城市和公开状态      |
| Target Discovery     | 按网络属性和公开状态同时筛选异网与跨省目标       |
| Result Receiver      | 接收并保存整分钟窗口探测结果                     |
| Alert Receiver       | 接收单次丢包告警事件并按用户告警类型路由通知     |
| Notification Service | 根据设备绑定关系及用户告警类型发送微信消息       |

### 3.2 Agent 模块

| 模块           | 职责                                                         |
| -------------- | ------------------------------------------------------------ |
| CLI / Config   | 首次配置和本地设备配置管理                                   |
| Scheduler      | 对齐自然分钟、校验目标上限、按 IP 版本合并去重并控制分钟边界 |
| Probe Engine   | 统一调度 ICMP、UDP 和 TCP Driver                             |
| Control Client | 绑定、目标查询、心跳、结果与告警事件上报                     |
| Local Buffer   | 中央服务不可用时暂存待发送的结果与告警事件                   |

## 4. 核心流程

### 4.1 启动与绑定

```mermaid
flowchart TD
    Start["用户启动程序"] --> Config["读取本地配置"]
    Config --> PublicIP["尝试获取当前设备公网 IPv4 和 IPv6"]
    PublicIP --> Status["使用 device_id 查询设备绑定状态"]
    Status --> Bound{"已绑定且仍关注服务号？"}
    Bound -- 否 --> QR["扫码关注服务号"]
    QR --> BindUpdate["绑定设备并更新设备 IP 信息"]
    BindUpdate --> Poll["轮询绑定结果"]
    Poll --> Bound
    Bound -- 是 --> Target["查询按分类与 IP 版本分组的目标 IP 列表"]
    Target --> Monitor["等待下一个自然分钟并开始探测"]
    Target -. "公众号用户设置" .-> AlertType["选择接收的告警类型"]
    AlertType -. "微信告警" .-> Monitor
```

流程说明如下：

1. Agent 读取 `device_id` 后分别尝试获取当前设备的公网 IPv4 和 IPv6，并暂存成功获取的地址。公网 IPv4 为启动必需项：获取失败时提示用户并阻塞重试，不进入绑定查询；公网 IPv6 获取失败不阻塞后续流程。IPv4 获取成功后查询绑定状态，未绑定或用户未关注服务号时展示 5 分钟有效的带参二维码并轮询绑定结果。
2. 用户关注或扫码后，中央服务完成用户与设备绑定，并将 Agent 获取到的公网 IPv4 和 IPv6 写入 `ip_dict`，关联到对应设备并更新网络属性。新用户的 `alert_type` 默认为 `1`，已有用户保留原设置；Agent 仅接收绑定状态。
3. 绑定成功后，Agent 使用当前公网 IPv4 和已成功获取的公网 IPv6 查询目标。中央服务始终返回异网和跨省 IPv4 列表；仅当 `source_ipv6` 有效时返回异网和跨省 IPv6 列表。Agent 按相同 IP 版本配对后开始持续探测，不要求用户选择探测类型或告警类型。
4. 用户可在微信服务号中将 `alert_type` 设置为 `1`（仅异网）、`2`（仅跨省）或 `3`（两类告警）。该设置对用户绑定的全部设备生效，只控制微信通知，不影响探测。

二维码使用 `QR_STR_SCENE`。`scene_str` 由北京时间 `YYMMDDHHMMSS` 和 4 位随机大写字母或数字组成，例如 `260731153045A7K2`；二维码及服务端记录均在 5 分钟后失效。

### 4.2 微信回调

- 微信服务器配置验证请求：完成签名校验并返回验证结果。
- 微信事件回调请求：接收关注、扫码和取消关注事件。

回调必须验证签名、限制请求体大小、幂等处理重复事件，并快速返回。取消关注后应停止向该用户发送通知。

用户可在微信服务号中修改自己的 `users.alert_type`；取消关注后保留该设置但停止通知，重新关注后恢复。

### 4.3 公开设备探测目标查询

Agent 提交 `device_id`、必填的 `source_ipv4`、可空的 `source_ipv6` 及设备身份校验字段，不提交用户选择的模式。中央服务校验非空源 IP 的版本和设备归属，在 `ip_dict` 中创建或复用记录，并刷新网络属性和 `update_time`。

中央服务分别以 IPv4、IPv6 源地址筛选同版本目标。候选 IP 必须合法、属于其他设备、`public_status = 1`、`update_time` 在有效期内，且关联设备的 `last_seen_at` 未超过离线阈值；两个阈值由中央服务统一配置。分类条件如下：

| 分类 | `probe_mode`     | 附加条件                                   |
| ---- | ------------------ | ------------------------------------------ |
| 异网 | `cross_isp`      | 源与目标的 ISP 均已识别且不同              |
| 跨省 | `cross_province` | 源与目标的省份均已识别、不是未知编码且不同 |

响应始终返回两个 IPv4 targets 列表；仅当 `source_ipv6` 有效时才返回两个 IPv6 targets 列表。若 Agent 未获取到 `source_ipv6`，请求和响应中的 `source_ipv6` 均为 `null`，响应省略 `cross_isp_ipv6_targets` 和 `cross_province_ipv6_targets`；Agent 将这两个字段缺失视为本轮无 IPv6 探测任务，不得视为响应格式错误。响应仅包含探测所需的公开信息。以下为 IPv4、IPv6 均可用时的完整示例：

```json
{
  "source_ipv4": "198.51.100.10",
  "source_ipv6": "2001:db8:100::10",
  "cross_isp_ipv4_targets": [
    {
      "public_ip": "203.0.113.20",
      "isp": 2,
      "province": 12
    }
  ],
  "cross_province_ipv4_targets": [
    {
      "public_ip": "198.51.100.30",
      "isp": 1,
      "province": 31
    }
  ],
  "cross_isp_ipv6_targets": [
    {
      "public_ip": "2001:db8:200::20",
      "isp": 2,
      "province": 12
    }
  ],
  "cross_province_ipv6_targets": [
    {
      "public_ip": "2001:db8:300::30",
      "isp": 1,
      "province": 31
    }
  ]
}
```

- 列表名称唯一确定 IP 版本，目标项不返回 `ip_version`；Agent 必须校验 `public_ip` 的实际地址族，不匹配时拒绝调度。
- 各列表按 `device_id`、`ip_dict.id` 升序返回并按 `ip_dict.id` 去重，供 Agent 按 `max_target_ip_count` 稳定截取；不得返回 `user_id`、`openid` 或告警设置。
- 同一 IP 可同时出现在同版本的两个分类列表中；Agent 保留其分类集合，合并后只探测一次，并将统计结果分别用于对应分类的结果和告警。

### 4.4 整分钟窗口探测

源地址、服务端返回列表与 Agent 实际探测列表的关系如下：

| 本机源地址 | 服务端返回的分类列表                                                                       | 实际探测的合并 IP 列表  |
| ---------- | ------------------------------------------------------------------------------------------ | ----------------------- |
| IPv4       | `cross_isp_ipv4_targets`、`cross_province_ipv4_targets`                                | `merged_ipv4_targets` |
| IPv6       | `cross_isp_ipv6_targets`、`cross_province_ipv6_targets`，仅 `source_ipv6` 有效时返回 | `merged_ipv6_targets` |

1. Agent 等待下一个 `HH:mm:00`，以该时刻到下一分钟 `HH:mm:00` 的完整 60 秒作为自然分钟窗口，并将 Context deadline 对齐窗口结束边界，不补做已开始的分钟。
2. Agent 刷新中央服务返回的两个 IPv4 目标列表，以及 `source_ipv6` 有效时返回的两个 IPv6 目标列表；每个已返回列表分别按顺序截取不超过 5.2 节定义的 `max_target_ip_count` 个目标。
3. Agent 将两个 IPv4 列表中的 `public_ip` 解析为规范地址并合并去重，生成内部列表 `merged_ipv4_targets`；存在 IPv6 列表时以相同方式生成 `merged_ipv6_targets`。
4. Agent 严格按相同 IP 版本执行探测：本机 IPv4 只探测 `merged_ipv4_targets`，本机 IPv6 只探测 `merged_ipv6_targets`。IPv6 不可用时不创建 `merged_ipv6_targets`。
5. Agent 为合并列表中的每个唯一 IP 固定生成 ICMP、TCP 和 UDP 三个逻辑目标，并为每个逻辑目标启动独立 goroutine，在窗口开始时同时探测，不创建子进程、不分批执行。同一 IP 同时属于两个分类时不得重复创建 Driver 探测任务。ICMP Driver 按 IP 版本复用共享 socket，UDP 和 TCP Driver 使用对应地址族的 socket 并绑定本次逻辑目标的源地址。
6. 每个逻辑目标在每个自然分钟窗口内固定执行 100 次探测。发送间隔由 `probe_interval = window_duration / probe_count` 计算；窗口固定为 60 秒，因此发送间隔为 `60s / 100 = 600ms`。
7. 第 `i` 次探测的计划发送时刻为 `window_start + i * probe_interval`，其中 `i` 从 0 到 99。Scheduler 使用基于窗口起点的绝对计划时刻，避免单次探测耗时造成累计漂移；最后一次发送时刻为窗口开始后的 59.4 秒。
8. 各 Driver 按协议语义匹配响应并生成统一结果；任一单次探测判定为丢包时，Probe Engine 按该 IP 的所属分类分别生成告警事件，不重复发送网络探测报文。
9. 窗口结束后分别计算各唯一目标三种协议的丢包率和成功响应平均延迟，再按目标的所属分类将同一份统计结果投影到对应 `probe_mode`，并以 `device_id + probe_mode + ip_version + source_ip` 分组写入 `targets` 数组后上报。每个可用源 IP 每个窗口分别为 `cross_isp` 和 `cross_province` 生成一份上报。

## 5. 统一探测模型

### 5.1 逻辑目标

每个实际探测目标使用稳定且唯一的 `target_id` 标识。Agent 根据 `ip_version`、`source_ip`、规范化后的目标 IP、协议和端口生成 `target_id`，`probe_mode` 不参与实际探测目标 ID 的生成；同一源目标组合同时属于异网和跨省时必须复用同一个 ID。目标由 IP 版本、源地址、目标地址、协议和端口共同定义，且源地址与目标地址的 IP 版本必须一致。每个合并后的唯一目标 IP 固定生成 ICMP、TCP 和 UDP 三个逻辑目标，各自独立统计；目标的所属分类集合只用于结果分组和告警事件生成。

| 协议 | 固定端口   | 成功条件                                                  | 延迟含义     |
| ---- | ---------- | --------------------------------------------------------- | ------------ |
| ICMP | 不使用端口 | 收到匹配的 ICMP/ICMPv6 Echo Reply                         | ICMP RTT     |
| TCP  | `80`     | TCP connect 成功，或收到 connection refused               | TCP 响应 RTT |
| UDP  | `33434`  | 收到目标 UDP 回复，或收到目标返回的 ICMP Port Unreachable | UDP 往返时间 |

TCP 固定探测端口 80。TCP connect 成功和 connection refused 均证明目标网络可达，二者都计为成功响应并纳入平均延迟；只有 TCP timeout、无响应或其他无法证明目标可达的错误才计为丢包。UDP 固定探测端口 33434，直接向目标 IP 和端口发送带匹配标识的 datagram，不发送 DNS 请求。目标端口开放但应用不回复、目标防火墙静默丢弃和网络丢包均可能表现为超时，因此 UDP timeout 计入丢包率时必须保留该语义限制。

### 5.2 默认参数

| 参数                                                    | 默认值                |
| ------------------------------------------------------- | --------------------- |
| 每目标每窗口探测次数                                    | 固定 100              |
| 发送间隔                                                | 60s / 100，固定 600ms |
| 单次探测超时                                            | 300ms                 |
| 自然分钟窗口                                            | 固定 60s              |
| 每个分类及 IP 版本最大目标数（`max_target_ip_count`） | 32                    |
| 探测目标分类                                            | 自动执行异网和跨省    |
| 探测协议                                                | 固定 ICMP、TCP、UDP   |

### 5.3 统一统计规则

```text
packet_loss_rate = (attempted_count - successful_count) / attempted_count * 100
average_latency = sum(successful_rtt) / successful_count
```

- 有效窗口必须完成 100 次探测，只统计超时前收到的合法且唯一响应。
- 平均延迟仅计算成功响应；100% 丢包时没有成功 RTT 样本，统一使用加大值 `1000ms`，不得返回 `null`。该值是丢包占位值，不代表真实 RTT，必须结合 `packet_loss_rate = 100` 判断。
- 各协议按统一成功条件分类；TCP connected 和 TCP refused 均计入成功。

### 5.4 协议 Driver

- **ICMP Driver**：使用 `golang.org/x/net/icmp` 收发 ICMPv4/ICMPv6 消息，按 IP 版本共享 socket 和接收 goroutine，将 socket 绑定到逻辑目标的 `source_ip`，并根据源 IP、目标 IP、Identifier 和 Sequence 匹配 Echo Reply。
- **TCP Driver**：使用与 `ip_version` 对应的 `net.Dialer`，通过 `LocalAddr` 绑定 `source_ip` 后建立 TCP 连接，连接成功后立即关闭；connection refused 表示主机可达但端口未开放，应按成功探测记录 RTT 并单独分类，不计入丢包率，也不产生丢包告警。TCP timeout 或无法证明目标可达的错误计为丢包。
- **UDP Driver**：使用与 `ip_version` 对应的 socket 并绑定 `source_ip`，直接向相同 IP 版本的目标地址和端口发送带匹配标识的 datagram，为每个未决探测分配可回收的唯一 source port，并根据五元组、payload 标识及 ICMP 引用的原始 UDP header 匹配目标 UDP 回复或 ICMP/ICMPv6 Port Unreachable；单纯成功发送 datagram 不视为探测成功。

各 Driver 只负责协议收发与单次结果分类。窗口调度、并发启动、统计汇总、结果上报和丢包告警由统一 Probe Engine 管理，避免为不同协议重复实现调度与上报逻辑。

## 6. 探测结果上报与告警

### 6.1 整分钟探测结果上报

每个整分钟窗口结束时，Agent 按 `device_id + probe_mode + ip_version + source_ip` 生成上报请求，并使用 `unix_timestamp` 标识窗口结束时间。同一分类、IP 版本和源 IP 下的全部目标汇总结果保存在 `targets` 数组中；对应目标列表为空时仍上报空 `targets`，用于表明该窗口已完成但没有符合条件的目标。中央服务校验 `source_ip` 属于 `device_id`，并校验 `targets` 中每个目标均已登记、与源 IP 的版本相同且等于顶层 `ip_version`。

```json
{
  "device_id": "source-device-id",
  "probe_mode": "cross_isp",
  "ip_version": 4,
  "source_ip": "198.51.100.10",
  "unix_timestamp": 1785542460,
  "targets": [
    {
      "target_ip": "203.0.113.20",
      "icmp": {
        "packet_loss_rate": 1.0,
        "average_latency_ms": 18.6
      },
      "tcp": {
        "packet_loss_rate": 0.0,
        "average_latency_ms": 25.4
      },
      "udp": {
        "packet_loss_rate": 2.0,
        "average_latency_ms": 21.8
      }
    }
  ]
}
```

中央服务以 `device_id + probe_mode + ip_version + source_ip + unix_timestamp` 作为上报幂等键，并以首次完整持久化的请求内容为准。中央服务根据 `device_id + source_ip` 查询源 IP 归属，再遍历 `targets`，根据全局唯一的 `target_ip` 查询目标 IP 记录及其 `device_related_id`，并校验源目标不是同一设备、两者 `ip_dict.ip_version` 均等于请求中的 `ip_version`，以及目标符合对应分类和公开状态；任一目标校验失败时拒绝整份上报。校验通过后，各目标结果按协议分别写入 `icmp_probe_state`、`tcp_probe_state` 和 `udp_probe_state`。空 `targets` 上报同样记录幂等状态，但不写入协议状态表。

### 6.2 单次丢包告警

任一单次探测未满足对应协议的成功条件时，Agent 立即按目标的所属分类分别上报告警事件，不等待窗口结束，也不设置阈值或重复告警抑制。同一 IP 同时属于异网和跨省时，一次实际探测丢包分别生成一条 `cross_isp` 和一条 `cross_province` 告警事件，但不得重复执行网络探测。TCP connection refused 仍按成功处理，不触发告警。

```json
{
  "event_id": "018f6c2e-7c45-7a9b-9ca1-2bd56f5d9310",
  "device_id": "source-device-id",
  "probe_mode": "cross_isp",
  "ip_version": 4,
  "source_ip": "198.51.100.10",
  "target_ip": "203.0.113.20",
  "protocol_type": "icmp",
  "unix_timestamp": 1785542412
}
```

`event_id` 作为告警幂等键；中央服务校验 `source_ip` 属于 `device_id`，根据全局唯一的 `target_ip` 查询目标 IP 记录及其设备归属，并校验源目标不是同一设备、IP 版本均与 `ip_version` 一致后，将事件写入 `alert_events`。用户仍关注服务号时，异网事件仅向 `alert_type` 为 `1` 或 `3` 的用户通知，跨省事件仅向 `alert_type` 为 `2` 或 `3` 的用户通知；通知正文持久化后再发送，不匹配的事件仅保存。

## 7. 数据设计

数据表中的内部主键、外键和 Unix 时间戳统一使用 `INT`；状态、协议和模式等有限选项使用整数编码，并通过 `CHECK` 约束合法取值。`VARCHAR` 和 `TEXT` 仅用于 `openid`、UUID、场景值、名称和消息正文等不可数值化的标识或文本。

### 7.1 `users`

| 字段                 | 数据类型         | 键                                     | 说明                                                       |
| -------------------- | ---------------- | -------------------------------------- | ---------------------------------------------------------- |
| `id`               | `INT`          | `PK`                                 | 用户内部主键，自增                                         |
| `openid`           | `VARCHAR(128)` | `UNIQUE`                             | 微信用户标识；扫码前允许为空，绑定完成后写入               |
| `scene_str`        | `VARCHAR(16)`  | `UNIQUE`                             | 字符串场景值，同时作为 Agent 轮询查询键                    |
| `subscribe_status` | `INT`          | -                                      | 当前是否关注服务号；`0` 表示未订阅，`1` 表示已订阅     |
| `alert_type`       | `INT`          | `NOT NULL`, `DEFAULT 1`, `CHECK` | 接收告警类型：`1`=仅异网、`2`=仅跨省、`3`=异网和跨省 |
| `created_time`     | `INT`          | -                                      | 创建时间，Unix 时间戳，单位秒                              |
| `updated_time`     | `INT`          | -                                      | 更新时间，Unix 时间戳，单位秒                              |

创建二维码时创建待绑定用户，`alert_type` 默认为 `1`；微信回调写入 `openid`。绑定轮询校验关注状态和场景有效期，完成设备关联后仅返回绑定状态。用户可在微信服务号中将 `alert_type` 修改为 `1`、`2` 或 `3`，该设置对其全部设备生效且不会因重新绑定或 Agent 重启而重置。

### 7.2 `ip_dict`

`ip_dict` 统一保存中央服务识别到的探测 IP 信息。

| 字段                  | 数据类型          | 键                                     | 说明                                             |
| --------------------- | ----------------- | -------------------------------------- | ------------------------------------------------ |
| `id`                | `INT`           | `PK`, `AUTO_INCREMENT`             | IP 记录自增主键                                  |
| `device_related_id` | `INT`           | `NOT NULL`, `FK → devices.id`     | IP 所属设备内部主键                              |
| `ip`                | `VARBINARY(16)` | `NOT NULL`, `UNIQUE`               | IP 二进制值；IPv4 为 4 字节，IPv6 为 16 字节     |
| `ip_version`        | `TINYINT`       | `NOT NULL`, `DEFAULT 4`, `CHECK` | IP 版本；仅允许`4` 或 `6`                    |
| `isp`               | `INT`           | -                                      | IP 对应的运营商编码                              |
| `province`          | `INT`           | -                                      | IP 对应的省份编码                                |
| `city`              | `VARCHAR(64)`   | -                                      | IP 对应的城市名称                                |
| `public_status`     | `INT`           | `NOT NULL`, `DEFAULT 1`, `CHECK` | IP 公开状态；`0` 表示未公开，`1` 表示公开    |
| `update_time`       | `INT`           | `NOT NULL`                           | IP 及其网络属性最近更新时间，Unix 时间戳，单位秒 |

同一设备可通过相同的 `device_related_id` 关联多条 `ip_dict` 记录。发现已属于该设备的 IP 时复用其 `id`，刷新网络属性和 `update_time`，但不得覆盖已有的 `public_status`；`ip` 的唯一约束保证同一个公网 IP 只对应一条记录。若同一 IP 已关联其他设备，中央服务必须拒绝静默改写归属并记录冲突，避免历史探测结果被错误归属。

### 7.3 `devices`

| 字段             | 数据类型        | 键                         | 说明                                                 |
| ---------------- | --------------- | -------------------------- | ---------------------------------------------------- |
| `id`           | `INT`         | `PK`, `AUTO_INCREMENT` | 设备记录自增主键                                     |
| `device_id`    | `VARCHAR(64)` | `UNIQUE`                 | Agent 首次绑定时生成的稳定设备标识                   |
| `user_id`      | `INT`         | `FK → users.id`         | 关联`users.id`；绑定前允许为空，关联用户删除后置空 |
| `last_seen_at` | `INT`         | -                          | 最后在线时间，Unix 时间戳，单位秒                    |
| `created_time` | `INT`         | -                          | 创建时间，Unix 时间戳，单位秒                        |
| `updated_time` | `INT`         | -                          | 更新时间，Unix 时间戳，单位秒                        |

绑定设备时，中央服务更新 `devices.user_id`，并将已获取的公网 IPv4/IPv6 写入或更新 `ip_dict`，关联对应 `devices.id`；新增 IP 不覆盖该设备已有记录。

### 7.4 `icmp_probe_state`

保存每个自然分钟窗口的 ICMP 探测状态。

| 字段             | 数据类型     | 键                                    | 说明                                          |
| ---------------- | ------------ | ------------------------------------- | --------------------------------------------- |
| `time_id`      | `INT`      | `PK` 组成部分，`INDEX`            | 窗口结束 Unix 时间戳，单位秒                  |
| `source_ip_id` | `INT`      | `PK` 组成部分，`FK → ip_dict.id` | 发起探测的源公网 IP 记录                      |
| `target_ip_id` | `INT`      | `PK` 组成部分，`FK → ip_dict.id` | 目标公网 IP 记录                              |
| `probe_mode`   | `INT`      | `PK` 组成部分，`CHECK`            | 目标分类：`1`=异网、`2`=跨省              |
| `loss_rate`    | `SMALLINT` | `NOT NULL`, `CHECK`               | ICMP 丢包率，整数范围为 0 至 1000，单位`‰` |
| `rtt_ms`       | `SMALLINT` | `NOT NULL`                          | ICMP 整数毫秒 RTT；100% 丢包时写入`1000`    |

### 7.5 `tcp_probe_state`

保存每个自然分钟窗口的 TCP 探测状态。

| 字段             | 数据类型     | 键                                    | 说明                                         |
| ---------------- | ------------ | ------------------------------------- | -------------------------------------------- |
| `time_id`      | `INT`      | `PK` 组成部分，`INDEX`            | 窗口结束 Unix 时间戳，单位秒                 |
| `source_ip_id` | `INT`      | `PK` 组成部分，`FK → ip_dict.id` | 发起探测的源公网 IP 记录                     |
| `target_ip_id` | `INT`      | `PK` 组成部分，`FK → ip_dict.id` | 目标公网 IP 记录                             |
| `probe_mode`   | `INT`      | `PK` 组成部分，`CHECK`            | 目标分类：`1`=异网、`2`=跨省             |
| `loss_rate`    | `SMALLINT` | `NOT NULL`, `CHECK`               | TCP 丢包率，整数范围为 0 至 1000，单位`‰` |
| `rtt_ms`       | `SMALLINT` | `NOT NULL`                          | TCP 整数毫秒 RTT；100% 丢包时写入`1000`    |

### 7.6 `udp_probe_state`

保存每个自然分钟窗口的 UDP 探测状态。

| 字段             | 数据类型     | 键                                    | 说明                                         |
| ---------------- | ------------ | ------------------------------------- | -------------------------------------------- |
| `time_id`      | `INT`      | `PK` 组成部分，`INDEX`            | 窗口结束 Unix 时间戳，单位秒                 |
| `source_ip_id` | `INT`      | `PK` 组成部分，`FK → ip_dict.id` | 发起探测的源公网 IP 记录                     |
| `target_ip_id` | `INT`      | `PK` 组成部分，`FK → ip_dict.id` | 目标公网 IP 记录                             |
| `probe_mode`   | `INT`      | `PK` 组成部分，`CHECK`            | 目标分类：`1`=异网、`2`=跨省             |
| `loss_rate`    | `SMALLINT` | `NOT NULL`, `CHECK`               | UDP 丢包率，整数范围为 0 至 1000，单位`‰` |
| `rtt_ms`       | `SMALLINT` | `NOT NULL`                          | UDP 整数毫秒 RTT；100% 丢包时写入`1000`    |

三张状态表均以 `time_id + source_ip_id + target_ip_id + probe_mode` 为复合主键。中央服务根据上报的 `source_ip` 解析源 `ip_dict.id`，并遍历 `targets`，根据每个全局唯一的 `target_ip` 解析目标 `ip_dict.id` 及其 `device_related_id`；源 IP 必须属于 `device_id`，源目标不能属于同一设备，且两者的 `ip_version` 必须相同并等于上报值，任一目标的归属、版本或分类不匹配时拒绝整份上报。`ip_version` 由 `source_ip_id` 和 `target_ip_id` 关联的 `ip_dict.ip_version` 保存，不在状态表中重复存储；`probe_mode` 转换为数值编码，`packet_loss_rate` 乘以 `10` 写入整数千分比 `loss_rate`，平均 RTT 四舍五入后写入 `rtt_ms`。固定探测 100 次时，`loss_rate` 以 `10‰` 为步长。

### 7.7 `alert_events`

告警事件按每次单次丢包保存，一条记录对应一次未满足协议成功条件的探测。

| 字段              | 数据类型        | 键                   | 说明                                           |
| ----------------- | --------------- | -------------------- | ---------------------------------------------- |
| `event_id`      | `VARCHAR(36)` | `PK`               | Agent 生成的事件唯一标识，同时作为告警幂等键   |
| `source_ip_id`  | `INT`         | `FK → ip_dict.id` | 发起探测的源公网 IP 记录                       |
| `target_ip_id`  | `INT`         | `FK → ip_dict.id` | 发生丢包的目标公网 IP 记录                     |
| `protocol_type` | `INT`         | `CHECK`            | 协议编码：`1`=ICMP、`2`=TCP、`3`=UDP     |
| `probe_mode`    | `INT`         | `CHECK`            | 目标分类编码：`1`=异网、`2`=跨省           |
| `occurred_at`   | `INT`         | -                    | 告警发生时间，Unix 时间戳，单位秒              |
| `message`       | `TEXT`        | -                    | 需要微信通知时生成的告警消息正文；未通知时为空 |

中央服务根据告警中的 `device_id` 和 `source_ip` 查询归属匹配的 `ip_dict.id` 并写入 `source_ip_id`，根据全局唯一的 `target_ip` 查询目标 `ip_dict.id` 及其 `device_related_id` 并写入 `target_ip_id`，同时校验源目标不是同一设备、两条 IP 记录的版本均等于上报的 `ip_version`，再将 `unix_timestamp` 写入 `occurred_at`。API 中的 `protocol_type` 和 `probe_mode` 转换为对应数值编码，`ip_version` 通过两个 IP 外键关联获取。事件分类符合源设备所属用户的 `alert_type` 且用户仍关注服务号时，中央服务生成并持久化 `message`；不符合时保存空值。

## 8. Agent 本地配置

```yaml
device:
  device_id: "5b65a1c8-6f23-4e10-b0c9-58ccaa1acd87"
```

本地配置暂时只保存 `device_id`，不包含 `monitor` 或告警类型配置块。Agent 每次启动并确认登录状态后自动获取两个 IPv4 目标列表；`source_ipv6` 有效时额外获取两个 IPv6 目标列表。每个已返回列表的目标数量分别遵循 5.2 节定义的 `max_target_ip_count`；Agent 将同版本的异网和跨省列表按规范化 IP 去重合并，本机 IPv4 只探测合并后的 IPv4 列表，本机 IPv6 只探测合并后的 IPv6 列表。合并后的每个唯一目标 IP 固定执行 ICMP、TCP 80 和 UDP 33434 三种探测。用户的告警类型设置只保存在中央服务，不下发或持久化到 Agent。

## 9. 异网探测告警

中央服务在设备绑定或刷新源地址时，分别查询公网 IPv4 和 IPv6 的 IP 归属信息，从匹配记录中提取运营商并写入对应 IP 记录的 `ip_dict.isp`：`1` 为电信、`2` 为移动、`3` 为联通、`4` 为其他。

Agent 查询目标时，中央服务为当前公网 IPv4 生成 `cross_isp_ipv4_targets`，并仅在 `source_ipv6` 有效时生成 `cross_isp_ipv6_targets`。每个列表只选择 `ip_dict.public_status = 1`、具有有效同版本公网 IP、归属于其他设备且 `ip_dict.isp` 与对应源 IP 不同的记录。候选目标不限于当前用户的设备；公开状态只授权将该公网 IP 用于探测，不授权返回设备绑定用户信息。运营商编码 `4` 表示其他运营商，只要与对应源 IP 的编码不同即可入选。Agent 无论用户的 `alert_type` 是否包含异网告警都执行可用地址族的异网列表探测；只有 `alert_type` 为 `1` 或 `3` 时才向该用户发送异网告警。

## 10. 跨省探测告警

中央服务将匹配记录的“省份-城市”字段拆分：省份归一化后写入 `ip_dict.province`（未知为 `1`），城市名称写入 `ip_dict.city`。

Agent 查询目标时，中央服务为当前公网 IPv4 生成 `cross_province_ipv4_targets`，并仅在 `source_ipv6` 有效时生成 `cross_province_ipv6_targets`。每个列表只选择 `ip_dict.public_status = 1`、具有有效同版本公网 IP、归属于其他设备且 `ip_dict.province` 与对应源 IP 不同的记录。对应源 IP 和候选 IP 的省份均必须已明确识别，未知省份不得参与跨省探测；ISP 是否相同不影响跨省分类的筛选结果。候选目标不限于当前用户的设备，城市仅用于展示和后续同省跨城市筛选。Agent 无论用户的 `alert_type` 是否包含跨省告警都执行可用地址族的跨省列表探测；只有 `alert_type` 为 `2` 或 `3` 时才向该用户发送跨省告警。

## 11. 部署方案

### 11.1 中央服务

中央服务使用 FastAPI 实现并部署在公网服务器，对外提供微信回调、绑定、轮询、设备管理、异网与跨省目标查询、分钟探测结果接收和丢包告警事件接收能力。具体 HTTP 路径和方法由实现阶段统一定义，不在本设计文档中固定。

### 11.2 Agent

Agent 编译为单个 Linux 二进制文件并部署到用户服务器，运行期间不创建探测子进程。运行前需授予 ICMP 探测和 UDP 错误接收所需的 ICMPv4/ICMPv6 socket 权限；启动时检查中央服务连接、服务端设备网络属性识别状态、ICMPv4/ICMPv6 socket、UDP 和 TCP 能力，检查通过后进入持续探测。

## 12. 实施计划

各阶段按依赖顺序实施，当前阶段通过验收后再进入下一阶段，避免同时扩展探测协议、设备管理和任务编排。

| 阶段     | 主要内容                                                                                                  |
| -------- | --------------------------------------------------------------------------------------------------------- |
| 第一阶段 | 基础服务与设备绑定：FastAPI、数据库迁移、微信回调、二维码绑定、设备身份及公网 IP 属性管理                 |
| 第二阶段 | 身份校验与目标发现：salt 签发与校验、IP 公开状态、ISP/省份识别、异网与跨省目标查询                        |
| 第三阶段 | 网络探测闭环：IPv4/IPv6 四组目标自动查询、同地址族分钟调度、ICMP/TCP/UDP 并发探测、结果上报和单次丢包告警 |
| 第四阶段 | 生产可靠性：双栈异常处理、UDP 直连探测、Local Buffer、幂等重试、`systemd` 和可观测性                    |
| 第五阶段 | 多设备管理：公众号设备列表、用户告警类型设置、Agent 定时心跳、在线/离线判定、公开状态管理和城市属性       |
| 第六阶段 | 双向 MTR：双向任务编排、租约控制、Golang Agent 原生 MTR、结果聚合与路径展示                               |

## 13. 后续功能支持

### 13.1 双向 MTR

#### 13.1.1 功能目标与边界

后续版本支持用户在中央服务选择两个在线设备，并为每个设备选择一条当前有效的公网 IP。两个设备上的 Golang Agent 分别执行 `设备 A 的 IP -> 设备 B 的 IP` 和 `设备 B 的 IP -> 设备 A 的 IP` 的 MTR，并将逐跳结果上报中央服务。两个方向使用同一个 `mtr_task_id` 关联，单方向失败时仍保留另一方向的成功结果。

#### 13.1.2 总体流程

1. 中央服务接收设备 A、设备 B 及各自选定的 `ip_dict.id`，校验两个设备已绑定、当前心跳在线、IP 归属匹配、处于公开状态且仍在有效期内。
2. 中央服务创建一个双向 MTR 主任务，并基于创建时的两个 IP ID 和二进制地址快照生成 `A_TO_B` 和 `B_TO_A` 两个方向任务。
3. Agent 通过现有 Control Client 主动轮询本设备待执行任务。中央服务不主动连接 Agent，以适配 NAT、防火墙和仅允许出站连接的部署环境。
4. 两个 Agent 分别执行本方向的 MTR，并幂等上报结果。
5. 中央服务聚合两个方向的状态和逐跳结果，供用户查询。

#### 13.1.3 执行与上报

中央服务通过方向租约避免任务重复执行，并保存两个方向的设备 ID、IP ID 和地址快照；任务开始前任一 IP 的设备归属、公开状态或有效期已变化时停止下发并将任务标记为过期。

Golang Agent 在进程内复用现有探测能力执行 ICMP MTR，不调用外部命令。目标仅允许中央服务下发的 IP 字面量。

Agent 以结构化 JSON 上报任务、方向、设备、IP、执行时间、逐跳统计和错误码。中央服务校验租约、方向及 IP 快照，以 `mtr_task_id + direction` 作为幂等键，并分别展示两个方向的路径。

### 13.2 基于 salt 校验 `device_id`

#### 13.2.1 校验方案

中央服务内置仅服务端可读取的 `DEVICE_ID_SALT`。设备绑定成功后，中央服务计算 `device_signature = HMAC-SHA256(DEVICE_ID_SALT, device_id)` 并返回给 Agent；Agent 将签名与 `device_id` 一同保存在本地配置中。

后续目标查询、心跳、结果上报、告警上报和 MTR 请求必须同时提交 `device_id` 与 `device_signature`。中央服务使用相同算法重新计算签名并进行常量时间比较，校验失败时拒绝请求。`device_id` 仍然只是设备标识，`device_signature` 才是设备持有中央服务签发凭据的证明。

### 13.3 内部控制器设备非公开处理

初期所有新建 IP 记录均使用 `ip_dict.public_status = 1`。后续中央服务识别出内部控制器设备后，将该设备关联的全部 `ip_dict.public_status` 强制设为 `0`；这些 IP 不得被异网、跨省或双向 MTR 的目标查询返回。普通 Agent 关联的 IP 继续使用默认公开状态，并允许用户通过多设备管理功能分别修改每条 IP 的公开状态。
