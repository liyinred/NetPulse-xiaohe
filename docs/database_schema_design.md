## 数据表结构设计

数据表中的内部主键和外键统一使用 `INT`，Unix 时间戳统一使用 `INT64`；状态、协议和模式等有限选项使用整数编码，并通过 `CHECK` 约束合法取值。`VARCHAR` 和 `TEXT` 仅用于 `openid`、UUID、场景值、名称和消息正文等不可数值化的标识或文本。临时 IP 查询的三协议结果作为一次不可拆分的节点响应，使用受固定 schema 校验的 `JSON` 字段保存。

### 7.1 `users`

| 字段                 | 数据类型         | 键                                     | 说明                                                       |
| -------------------- | ---------------- | -------------------------------------- | ---------------------------------------------------------- |
| `id`               | `INT`          | `PK`                                 | 用户内部主键，自增                                         |
| `openid`           | `VARCHAR(128)` | `UNIQUE`                             | 有效微信用户标识；无有效值时不创建用户记录                 |
| `scene_str`        | `VARCHAR(16)`  | `UNIQUE`                             | 字符串场景值，同时作为 Agent 轮询查询键                    |
| `subscribe_status` | `INT`          | -                                      | 当前是否关注服务号；`0` 表示未订阅，`1` 表示已订阅     |
| `alert_type`       | `INT`          | `NOT NULL`, `DEFAULT 1`, `CHECK` | 接收告警类型：`1`=仅异网、`2`=仅跨省、`3`=异网和跨省 |
| `user_level`       | `INT`          | `NOT NULL`, `DEFAULT 1`, `CHECK` | 用户等级：`1`=普通用户、`2`=高级用户、`9`=管理员       |
| `created_time`     | `INT64`        | -                                      | 创建时间，Unix 时间戳，单位秒                              |
| `updated_time`     | `INT64`        | -                                      | 更新时间，Unix 时间戳，单位秒                              |

创建二维码时不预写用户记录；微信回调取得有效 `openid` 后才创建或更新用户，`alert_type` 和 `user_level` 均默认为 `1`。`user_level` 仅允许 `1`、`2` 或 `9`，分别表示普通用户、高级用户和管理员。绑定轮询校验关注状态和场景有效期，完成设备关联后仅返回绑定状态。用户可在微信服务号中将 `alert_type` 修改为 `1`、`2` 或 `3`，该设置对其全部设备生效且不会因重新绑定或 Agent 重启而重置。

### 7.2 `ip_dict`

`ip_dict` 统一保存中央服务识别到的探测 IP 信息，不强制绑定设备。

| 字段                  | 数据类型          | 键                                     | 说明                                                |
| --------------------- | ----------------- | -------------------------------------- | --------------------------------------------------- |
| `id`                | `INT`           | `PK`, `AUTO_INCREMENT`             | IP 记录自增主键                                     |
| `device_related_id` | `INT`           | `FK → devices.id`                   | IP 所属设备内部主键；允许为空，空值表示尚未关联设备 |
| `ip`                | `VARCHAR(45)` | `NOT NULL`, `UNIQUE`               | 规范化 IP 文本；同时支持 IPv4 和 IPv6               |
| `ip_version`        | `INT`           | `NOT NULL`, `DEFAULT 4`, `CHECK` | IP 版本；仅允许`4` 或 `6`                       |
| `isp`               | `INT`           | -                                      | IP 对应的运营商编码                                 |
| `province`          | `INT`           | -                                      | IP 对应的省份编码                                   |
| `city`              | `VARCHAR(64)`   | -                                      | IP 对应的城市名称                                   |
| `public_status`     | `INT`           | `NOT NULL`, `DEFAULT 1`, `CHECK` | IP 公开状态；`0` 表示未公开，`1` 表示公开       |
| `update_time`       | `INT64`         | `NOT NULL`                           | IP 及其网络属性最近更新时间，Unix 时间戳，单位秒    |

#### 7.2.1 运营商编号规则

FastAPI 服务通过 `normalize_isp` 将 IP 归属查询接口返回的运营商名称转换为 `isp` 编号。匹配采用名称包含判断，并按电信、移动、联通的顺序执行；未匹配到这三类的运营商统一归为其他。

编号规则为：`1`=电信，名称包含“电信”；`2`=移动，名称包含“移动”；`3`=联通，名称包含“联通”；`4`=其他，包括空值、未知名称或未匹配以上关键字的名称。

#### 7.2.2 省份编号规则

FastAPI 服务通过 `normalize_province` 将 IP 归属查询接口返回的省份名称转换为 `province` 编号。转换前先清除首尾空白和开头的“中国”，再清除末尾的“壮族自治区”“回族自治区”“维吾尔自治区”“特别行政区”“自治区”“省”或“市”；空值、未知名称或未匹配到以下名称时统一使用编号 `1`。

编号规则为：`1`=未知，`2`=北京，`3`=福建，`4`=甘肃，`5`=广东，`6`=广西，`7`=贵州，`8`=海南，`9`=河北，`10`=河南，`11`=黑龙江，`12`=湖北，`13`=湖南，`14`=吉林，`15`=江苏，`16`=江西，`17`=辽宁，`18`=内蒙古，`19`=宁夏，`20`=青海，`21`=山东，`22`=山西，`23`=陕西，`24`=上海，`25`=四川，`26`=天津，`27`=西藏，`28`=新疆，`29`=云南，`30`=浙江，`31`=重庆，`32`=安徽，`33`=香港，`34`=台湾，`35`=澳门。

同一设备可通过相同的 `device_related_id` 关联多条 `ip_dict` 记录。IP 记录创建时允许 `device_related_id` 为空，后续确认设备归属时可将其更新为对应的 `devices.id`。发现已属于该设备的 IP 时复用其 `id`，刷新网络属性和 `update_time`，但不得覆盖已有的 `public_status`；`ip` 的唯一约束保证同一个公网 IP 只对应一条记录。

### 7.3 `devices`

| 字段                 | 数据类型        | 键                                     | 说明                                                        |
| -------------------- | --------------- | -------------------------------------- | ----------------------------------------------------------- |
| `id`               | `INT`         | `PK`, `AUTO_INCREMENT`             | 设备记录自增主键                                            |
| `device_id`        | `VARCHAR(64)` | `UNIQUE`                             | Agent 首次绑定时生成的稳定设备标识                          |
| `user_id`          | `INT`         | `FK → users.id`                     | 关联`users.id`；绑定前允许为空，关联用户删除后置空        |
| `on_demand_status` | `INT`         | `NOT NULL`, `DEFAULT 1`, `CHECK` | 是否接受临时 IP 按需任务；`0`=关闭、`1`=开启            |
| `last_seen_at`     | `INT64`       | -                                      | 最近一次通过身份校验的控制任务轮询时间，Unix 时间戳，单位秒 |
| `created_time`     | `INT64`       | -                                      | 创建时间，Unix 时间戳，单位秒                               |
| `updated_time`     | `INT64`       | -                                      | 更新时间，Unix 时间戳，单位秒                               |

绑定设备时，中央服务更新 `devices.user_id`，并将已获取的公网 IPv4/IPv6 写入或更新 `ip_dict`，关联对应 `devices.id`；新增 IP 不覆盖该设备已有记录。`on_demand_status` 默认开启，用户后续可在多设备管理中关闭单个设备的按需探测能力；关闭只阻止新任务创建，已进入执行中的任务允许完成并上报。

持续探测状态表统一采用 `probe_state_{type}` 命名格式，其中 `{type}` 为小写协议名称。

### 7.4 `probe_state_icmp`

保存每个自然分钟窗口的 ICMP 探测状态。

| 字段             | 数据类型  | 键                                    | 说明                                       |
| ---------------- | --------- | ------------------------------------- | ------------------------------------------ |
| `time_id`      | `INT64` | `PK` 组成部分，`INDEX`            | 窗口结束 Unix 时间戳，单位秒               |
| `device_related_id` | `INT` | `NOT NULL`, `FK → devices.id`   | 上报该分钟结果的设备内部主键               |
| `source_ip_id` | `INT`   | `PK` 组成部分，`FK → ip_dict.id` | 发起探测的源公网 IP 记录                   |
| `target_ip_id` | `INT`   | `PK` 组成部分，`FK → ip_dict.id` | 目标公网 IP 记录                           |
| `probe_mode`   | `INT`   | `PK` 组成部分，`CHECK`            | 目标分类：`1`=异网、`2`=跨省           |
| `loss_rate`    | `INT`   | `NOT NULL`, `CHECK`               | ICMP 丢包率，0 至 1000 的整数千分比        |
| `rtt_ms`       | `INT`   | `NOT NULL`                          | ICMP 整数毫秒 RTT；100% 丢包时写入`1000` |

### 7.5 `probe_state_tcp`

保存每个自然分钟窗口的 TCP 探测状态。

| 字段             | 数据类型  | 键                                    | 说明                                      |
| ---------------- | --------- | ------------------------------------- | ----------------------------------------- |
| `time_id`      | `INT64` | `PK` 组成部分，`INDEX`            | 窗口结束 Unix 时间戳，单位秒              |
| `device_related_id` | `INT` | `NOT NULL`, `FK → devices.id`   | 上报该分钟结果的设备内部主键              |
| `source_ip_id` | `INT`   | `PK` 组成部分，`FK → ip_dict.id` | 发起探测的源公网 IP 记录                  |
| `target_ip_id` | `INT`   | `PK` 组成部分，`FK → ip_dict.id` | 目标公网 IP 记录                          |
| `probe_mode`   | `INT`   | `PK` 组成部分，`CHECK`            | 目标分类：`1`=异网、`2`=跨省          |
| `loss_rate`    | `INT`   | `NOT NULL`, `CHECK`               | TCP 丢包率，0 至 1000 的整数千分比        |
| `rtt_ms`       | `INT`   | `NOT NULL`                          | TCP 整数毫秒 RTT；100% 丢包时写入`1000` |

### 7.6 `probe_state_udp`

保存每个自然分钟窗口的 UDP 探测状态。

| 字段             | 数据类型  | 键                                    | 说明                                      |
| ---------------- | --------- | ------------------------------------- | ----------------------------------------- |
| `time_id`      | `INT64` | `PK` 组成部分，`INDEX`            | 窗口结束 Unix 时间戳，单位秒              |
| `device_related_id` | `INT` | `NOT NULL`, `FK → devices.id`   | 上报该分钟结果的设备内部主键              |
| `source_ip_id` | `INT`   | `PK` 组成部分，`FK → ip_dict.id` | 发起探测的源公网 IP 记录                  |
| `target_ip_id` | `INT`   | `PK` 组成部分，`FK → ip_dict.id` | 目标公网 IP 记录                          |
| `probe_mode`   | `INT`   | `PK` 组成部分，`CHECK`            | 目标分类：`1`=异网、`2`=跨省          |
| `loss_rate`    | `INT`   | `NOT NULL`, `CHECK`               | UDP 丢包率，0 至 1000 的整数千分比        |
| `rtt_ms`       | `INT`   | `NOT NULL`                          | UDP 整数毫秒 RTT；100% 丢包时写入`1000` |

三张状态表均以 `time_id + source_ip_id + target_ip_id + probe_mode` 为复合主键。中央服务根据上报的 `device_id` 查询已绑定设备，将其内部主键写入每条状态记录的 `device_related_id`；再根据上报的 `source_ip` 解析源 `ip_dict.id`，并遍历 `targets`，根据每个全局唯一的 `target_ip` 解析目标 `ip_dict.id`。源 IP 必须属于该设备，目标 IP 不要求关联设备但不得属于当前设备，且两者的 `ip_version` 必须相同并等于上报值，任一目标的归属、版本或分类不匹配时拒绝整份上报。`ip_version` 由 `source_ip_id` 和 `target_ip_id` 关联的 `ip_dict.ip_version` 保存，不在状态表中重复存储；`probe_mode` 转换为数值编码，API 中的整数千分比 `loss_rate` 和整数毫秒 `average_latency_ms` 分别直接写入 `loss_rate` 与 `rtt_ms`。幂等重试除比较丢包率和 RTT 外，也比较已有记录的 `device_related_id`。

### 7.7 `alert_events`

告警事件按自然分钟、源地址、目标地址、协议和分类聚合保存；一个聚合维度在同一窗口内最多保存一条记录。

| 字段              | 数据类型        | 键                   | 说明                                           |
| ----------------- | --------------- | -------------------- | ---------------------------------------------- |
| `event_id`      | `VARCHAR(36)` | `PK`               | Agent 生成的事件唯一标识，同时作为告警幂等键   |
| `device_related_id` | `INT`       | `NOT NULL`, `FK → devices.id` | 上报该告警事件的设备内部主键       |
| `source_ip_id`  | `INT`         | `FK → ip_dict.id` | 发起探测的源公网 IP 记录                       |
| `target_ip_id`  | `INT`         | `FK → ip_dict.id` | 发生丢包的目标公网 IP 记录                     |
| `protocol_type` | `INT`         | `CHECK`            | 协议编码：`1`=ICMP、`2`=TCP、`3`=UDP     |
| `probe_mode`    | `INT`         | `CHECK`            | 目标分类编码：`1`=异网、`2`=跨省           |
| `occurred_at`   | `INT64`       | -                    | 自然分钟窗口结束时间，Unix 时间戳，单位秒      |
| `message`       | `TEXT`        | -                    | 包含分类、协议及源目标地址的告警事件摘要       |

中央服务根据告警中的 `device_id` 查询已绑定设备，将其内部主键写入 `device_related_id`，并结合 `source_ip` 查询归属匹配的 `ip_dict.id` 写入 `source_ip_id`；根据全局唯一的 `target_ip` 查询目标 `ip_dict.id` 写入 `target_ip_id`，同时校验目标不属于当前设备、两条 IP 记录的版本均等于上报的 `ip_version`，再将 `unix_timestamp` 写入 `occurred_at`。目标 IP 不要求关联设备。API 中的 `protocol_type` 和 `probe_mode` 转换为对应数值编码，`ip_version` 通过两个 IP 外键关联获取。事件记录始终保存 `message`；发送服务号模板消息时，中央服务直接通过 `alert_events.device_related_id` 查询 `devices.user_id`，再查询对应用户的 `openid`、关注状态和 `alert_type`，仅向仍关注且告警类型匹配的用户发送通知。

### 7.8 `on_demand_executions`

一条记录对应一次可以被多个用户查询共享的实际探测执行。

| 字段                | 数据类型          | 键                         | 说明                                                           |
| ------------------- | ----------------- | -------------------------- | -------------------------------------------------------------- |
| `id`              | `INT`           | `PK`, `AUTO_INCREMENT` | 执行内部主键                                                   |
| `target_ip`       | `VARCHAR(45)` | `NOT NULL`               | 规范化临时目标 IP 文本快照                                     |
| `ip_version`      | `INT`           | `NOT NULL`, `CHECK`    | IP 版本；仅允许`4` 或 `6`                                  |
| `target_isp`      | `INT`           | -                          | 创建时识别的目标 ISP                                           |
| `target_province` | `INT`           | -                          | 创建时识别的目标省份                                           |
| `active_key`      | `VARCHAR(64)`   | `UNIQUE`                 | 活动执行去重键，进入终态后置空                                 |
| `status`          | `INT`           | `NOT NULL`, `CHECK`    | `1`=排队、`2`=执行、`3`=完成、`4`=部分完成、`5`=失败 |
| `created_at`      | `INT64`         | `NOT NULL`               | 创建时间                                                       |
| `started_at`      | `INT64`         | -                          | 首个节点开始时间                                               |
| `finished_at`     | `INT64`         | -                          | 执行进入终态的时间                                             |

`active_key` 由查询的目标IP生成。中央服务在事务内插入活动执行，唯一键冲突时复用已有执行记录 `id`；执行进入终态后将 `active_key` 置空。目标及网络属性直接保存在执行中，不再单独维护临时 IP 字典。

### 7.9 `probe_queries`

一条记录对应一个用户发起的临时 IP 查询，是访问控制、配额和查询历史的边界。

| 字段             | 数据类型  | 键                                | 说明                     |
| ---------------- | --------- | --------------------------------- | ------------------------ |
| `id`           | `INT`   | `PK`, `AUTO_INCREMENT`        | 用户查询内部主键         |
| `user_id`      | `INT`   | `FK → users.id`, `INDEX`     | 发起查询的用户           |
| `execution_id` | `INT`   | `FK → on_demand_executions.id` | 关联的实际执行           |
| `created_at`   | `INT64` | `NOT NULL`                      | 创建时间                 |
| `expires_at`   | `INT64` | `NOT NULL`                      | 用户可读取结果的截止时间 |

即使多个查询关联同一 `execution_id`，也必须分别保留自己的 `id`。查询状态直接取关联执行的状态；结果查询以查询记录 `id + user_id` 校验权限。

### 7.10 `on_demand_node_tasks`

保存一次执行分配给每个在线节点的任务状态和探测结果。

| 字段                | 数据类型  | 键                                | 说明                                                           |
| ------------------- | --------- | --------------------------------- | -------------------------------------------------------------- |
| `id`              | `INT`   | `PK`, `AUTO_INCREMENT`        | 节点任务及结果幂等键                                           |
| `execution_id`    | `INT`   | `FK → on_demand_executions.id` | 所属执行                                                       |
| `probe_device_id` | `INT`   | `FK → devices.id`              | 执行探测的 Agent 设备内部主键                                  |
| `source_ip_id`    | `INT`   | `FK → ip_dict.id`              | 选定的节点源 IP                                                |
| `probe_modes`     | `INT`   | `NOT NULL`, `CHECK`           | 分类集合：`1`=异网、`2`=跨省、`3`=两者                   |
| `status`          | `INT`   | `NOT NULL`, `CHECK`           | `1`=待领取、`2`=执行中、`3`=完成、`4`=超时、`5`=失败 |
| `result_data`     | `JSON`  | -                                 | 三种协议的整数千分比丢包率和整数毫秒平均延迟                   |
| `started_at`      | `INT64` | -                                 | 节点开始执行时间                                               |
| `finished_at`     | `INT64` | -                                 | 节点任务完成时间                                               |

`execution_id + probe_device_id` 必须唯一，保证同一设备只执行一次。节点源 IP、ISP 和省份通过 `source_ip_id` 关联 `ip_dict` 获取，不重复保存快照；被节点任务引用的 `ip_dict` 记录不得硬删除，也不得原地修改 `ip`。任务完成时在同一事务内写入完整 `result_data` 并将状态改为完成；失败或超时时 `result_data` 为空。`result_data` 必须包含 `icmp`、`tcp`、`udp` 三项，每项的 `loss_rate` 为 0 至 1000 的整数千分比，`average_latency_ms` 为整数。
