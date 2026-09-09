## 数据表结构设计

数据表中的内部主键和外键统一使用 `INT`，Unix 时间戳统一使用 `INT64`；状态、协议和模式等有限选项使用整数编码，并通过 `CHECK` 约束合法取值。`VARCHAR` 和 `TEXT` 仅用于不可数值化的标识或文本。即时 IP 节点结果使用固定 schema 的 `JSON` 保存，其中 ICMP、TCP 必填，UDP 未启用时允许为 `null`。

### 7.1 `users`

| 字段                 | 数据类型         | 键                                     | 说明                                                       |
| -------------------- | ---------------- | -------------------------------------- | ---------------------------------------------------------- |
| `id`               | `INT`          | `PK`                                 | 用户内部主键，自增                                         |
| `openid`           | `VARCHAR(128)` | `UNIQUE`                             | 有效微信用户标识；无有效值时不创建用户记录                 |
| `scene_str`        | `VARCHAR(16)`  | `UNIQUE`                             | 字符串场景值，同时作为 Agent 轮询查询键                    |
| `subscribe_status` | `INT`          | -                                      | 当前是否关注服务号；`0` 表示未订阅，`1` 表示已订阅     |
| `alert_type`       | `INT`          | `NOT NULL`, `DEFAULT 1`, `CHECK` | 接收告警类型：`0`=不接收服务号告警、`1`=仅异网、`2`=仅跨省、`3`=异网和跨省 |
| `user_level`       | `INT`          | `NOT NULL`, `DEFAULT 1`, `CHECK` | 用户等级：`1`=普通用户、`2`=高级用户、`9`=管理员       |
| `created_time`     | `INT64`        | -                                      | 创建时间，Unix 时间戳，单位秒                              |
| `updated_time`     | `INT64`        | -                                      | 更新时间，Unix 时间戳，单位秒                              |

创建二维码时不预写用户记录；微信回调取得有效 `openid` 后才创建或更新用户，`alert_type` 和 `user_level` 均默认为 `1`。`alert_type` 仅允许 `0`、`1`、`2` 或 `3`；设置为 `0` 后不接收任何服务号告警，但不影响持续探测及告警事件入库。`user_level` 仅允许 `1`、`2` 或 `9`，分别表示普通用户、高级用户和管理员。绑定轮询校验关注状态和场景有效期，完成设备关联后仅返回绑定状态。用户可通过用户管理页面修改 `alert_type`，该设置对其全部设备生效且不会因重新绑定或 Agent 重启而重置。

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

同一设备可通过相同的 `device_related_id` 关联多条 `ip_dict` 记录。IP 记录创建时允许 `device_related_id` 为空，后续确认设备归属时可将其更新为对应的 `devices.id`。发现已属于该设备的 IP 时复用其 `id`，仅在设备关联、IP 版本或网络属性变化时刷新 `update_time`，且不得覆盖已有的 `public_status`；`ip` 的唯一约束保证同一个公网 IP 只对应一条记录。

### 7.3 `devices`

| 字段                 | 数据类型        | 键                                     | 说明                                                        |
| -------------------- | --------------- | -------------------------------------- | ----------------------------------------------------------- |
| `id`               | `INT`         | `PK`, `AUTO_INCREMENT`             | 设备记录自增主键                                            |
| `device_id`        | `VARCHAR(64)` | `UNIQUE`                             | Agent 首次绑定时生成的稳定设备标识                          |
| `user_id`          | `INT`         | `FK → users.id`                     | 关联`users.id`；绑定前允许为空，关联用户删除后置空        |
| `on_demand_status` | `INT`         | `NOT NULL`, `DEFAULT 1`, `CHECK` | 是否接受即时 IP 按需任务；`0`=关闭、`1`=开启            |
| `last_seen_at`     | `INT64`       | -                                      | 最近一次通过身份校验的控制任务轮询时间，Unix 时间戳，单位秒 |
| `created_time`     | `INT64`       | -                                      | 创建时间，Unix 时间戳，单位秒                               |

绑定设备时，中央服务更新 `devices.user_id`，并将已获取的公网 IPv4/IPv6 写入或更新 `ip_dict`，关联对应 `devices.id`；新增 IP 不覆盖该设备已有记录。`on_demand_status` 默认开启，用户后续可在多设备管理中关闭单个设备的按需探测能力；关闭只阻止新任务创建，已进入执行中的任务允许完成并上报。

持续探测状态表统一采用 `probe_state_{type}` 命名格式，其中 `{type}` 为小写协议名称。

### 7.4 `probe_state_icmp`

保存每个自然分钟窗口的 ICMP 探测状态。

| 字段             | 数据类型  | 键                                    | 说明                                       |
| ---------------- | --------- | ------------------------------------- | ------------------------------------------ |
| `time_id`      | `INT64` | `PK` 组成部分，`INDEX`            | 窗口结束 Unix 时间戳，单位秒               |
| `device_related_id` | `INT` | `NOT NULL`, `FK → devices.id`   | 上报该分钟结果的设备内部主键               |
| `source_ip_id` | `INT`   | `PK` 组成部分 | 发起探测的源公网 IP 记录 ID（逻辑关联）    |
| `target_ip_id` | `INT`   | `PK` 组成部分 | 目标公网 IP 记录 ID（逻辑关联）            |
| `probe_mode`   | `INT`   | `PK` 组成部分，`CHECK`            | 目标分类：`1`=异网、`2`=跨省           |
| `loss_rate`    | `INT`   | `NOT NULL`, `CHECK`               | ICMP 丢包率，0 至 1000 的整数千分比        |
| `rtt_ms`       | `INT`   | `NOT NULL`, `CHECK`                 | ICMP 整数毫秒 RTT，范围 0 至 300；100% 丢包时写入 `300` |

### 7.5 `probe_state_tcp`

保存每个自然分钟窗口的 TCP 探测状态。

| 字段             | 数据类型  | 键                                    | 说明                                      |
| ---------------- | --------- | ------------------------------------- | ----------------------------------------- |
| `time_id`      | `INT64` | `PK` 组成部分，`INDEX`            | 窗口结束 Unix 时间戳，单位秒              |
| `device_related_id` | `INT` | `NOT NULL`, `FK → devices.id`   | 上报该分钟结果的设备内部主键              |
| `source_ip_id` | `INT`   | `PK` 组成部分 | 发起探测的源公网 IP 记录 ID（逻辑关联）   |
| `target_ip_id` | `INT`   | `PK` 组成部分 | 目标公网 IP 记录 ID（逻辑关联）           |
| `probe_mode`   | `INT`   | `PK` 组成部分，`CHECK`            | 目标分类：`1`=异网、`2`=跨省          |
| `loss_rate`    | `INT`   | `NOT NULL`, `CHECK`               | TCP 丢包率，0 至 1000 的整数千分比        |
| `rtt_ms`       | `INT`   | `NOT NULL`, `CHECK`                 | TCP 整数毫秒 RTT，范围 0 至 300；100% 丢包时写入 `300` |

### 7.6 `probe_state_udp`

保存每个自然分钟窗口中已启用的 UDP 探测状态；目标 Agent 不在线时不生成对应记录。

| 字段             | 数据类型  | 键                                    | 说明                                      |
| ---------------- | --------- | ------------------------------------- | ----------------------------------------- |
| `time_id`      | `INT64` | `PK` 组成部分，`INDEX`            | 窗口结束 Unix 时间戳，单位秒              |
| `device_related_id` | `INT` | `NOT NULL`, `FK → devices.id`   | 上报该分钟结果的设备内部主键              |
| `source_ip_id` | `INT`   | `PK` 组成部分 | 发起探测的源公网 IP 记录 ID（逻辑关联）   |
| `target_ip_id` | `INT`   | `PK` 组成部分 | 目标公网 IP 记录 ID（逻辑关联）           |
| `probe_mode`   | `INT`   | `PK` 组成部分，`CHECK`            | 目标分类：`1`=异网、`2`=跨省          |
| `loss_rate`    | `INT`   | `NOT NULL`, `CHECK`               | UDP 丢包率，0 至 1000 的整数千分比        |
| `rtt_ms`       | `INT`   | `NOT NULL`, `CHECK`                 | UDP 整数毫秒 RTT，范围 0 至 300；100% 丢包时写入 `300` |

三张状态表均以 `time_id + source_ip_id + target_ip_id + probe_mode` 为复合主键，并各自维护非唯一复合索引 `ix_probe_state_{type}_time_source_mode`（`time_id + source_ip_id + probe_mode`），用于按分钟窗口、源 IP 和探测分类查询已有结果以完成幂等校验。中央服务校验设备、源目标 IP、版本和分类后，将非空协议结果写入对应状态表；ICMP、TCP 固定写入，UDP 为 `null` 时跳过 `probe_state_udp`。其余字段映射和幂等比较规则相同。

### 7.7 `alert_events`

新增记录仅保存中央服务状态机产生的故障、提醒、恢复事件，按用户设置通知。原有 Agent 分钟事件历史记录保留。

| 字段              | 数据类型        | 键                   | 说明                                           |
| ----------------- | --------------- | -------------------- | ---------------------------------------------- |
| `event_id`      | `VARCHAR(36)` | `PK`               | Agent 或中央服务生成的 UUID，同时作为事件幂等键   |
| `device_related_id` | `INT`       | `NOT NULL`, `FK → devices.id` | 上报该告警事件的设备内部主键       |
| `source_ip_id`  | `INT`         | - | 发起探测的源公网 IP 记录 ID（逻辑关联）          |
| `target_ip_id`  | `INT`         | - | 发生丢包的目标公网 IP 记录 ID（逻辑关联）        |
| `protocol_type` | `INT`         | `CHECK`            | 协议编码：`1`=ICMP、`2`=TCP、`3`=UDP     |
| `probe_mode`    | `INT`         | `CHECK`            | 目标分类编码：`1`=异网、`2`=跨省           |
| `occurred_at`   | `INT64`       | -                    | 自然分钟窗口结束时间，Unix 时间戳，单位秒      |
| `message`       | `TEXT`        | -                    | 包含分类、协议及源目标地址的告警事件摘要       |

事件经设备归属、目标和分类校验后入库；中央服务事件的 `message` 包含事件类型和丢包率。

#### `probe_alert_states`

持久化跨分钟告警状态，联合主键为 `(source_ip_id, target_ip_id, probe_mode, protocol_type)`。

| 字段 | 数据类型 | 说明 |
| --- | --- | --- |
| `source_ip_id`、`target_ip_id` | `INT NOT NULL` | 源、目标 IP 逻辑关联 |
| `probe_mode`、`protocol_type` | `INT NOT NULL` | 分类、协议编码，同事件表 |
| `is_firing` | `BOOL NOT NULL` | 是否已确认故障 |
| `abnormal_count`、`normal_count` | `INT NOT NULL` | 连续异常、正常窗口数，上限 2 |
| `fault_started_at` | `BIGINT NULL` | 故障开始时间，恢复后清空 |
| `last_notified_at` | `BIGINT NULL` | 最近通知决策时间，不代表送达 |
| `last_window_at` | `BIGINT NOT NULL` | 最后处理窗口，用于去重和连续性判断 |

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

`active_key` 由查询的目标IP生成。中央服务在事务内插入活动执行，唯一键冲突时复用已有执行记录 `id`；执行进入终态后将 `active_key` 置空。目标及网络属性直接保存在执行中，不再单独维护即时 IP 字典。

### 7.9 `probe_queries`

一条记录对应一个用户发起的即时 IP 查询，是访问控制、配额和查询历史的边界。

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
| `source_ip_id`    | `INT`   | -                               | 选定节点源 IP 的内部主键快照，不建立外键                        |
| `probe_modes`     | `INT`   | `NOT NULL`, `CHECK`           | 分类集合：`1`=异网、`2`=跨省、`3`=两者                   |
| `status`          | `INT`   | `NOT NULL`, `CHECK`           | `1`=待领取、`2`=执行中、`3`=完成、`4`=超时、`5`=失败 |
| `result_data`     | `JSON`  | -                                 | ICMP、TCP 及可选 UDP 的丢包率和平均延迟                         |
| `started_at`      | `INT64` | -                                 | 节点开始执行时间                                               |
| `finished_at`     | `INT64` | -                                 | 节点任务完成时间                                               |

`execution_id + probe_device_id` 必须唯一。任务完成时在同一事务内写入 `result_data` 并将状态改为完成；失败或超时时为空。`result_data` 中 `icmp`、`tcp` 必填，`udp` 在目标 Agent 不在线时为 `null`；非空协议结果包含整数千分比 `loss_rate` 和整数毫秒 `average_latency_ms`。

### 7.11 `bidirectional_mtr_tasks`

保存用户创建的一次双向 MTR 主任务。

| 字段 | 数据类型 | 键 | 说明 |
| --- | --- | --- | --- |
| `id` | `INT` | `PK`, `AUTO_INCREMENT` | 主任务内部主键，也是两个方向共用的 `mtr_task_id` |
| `user_id` | `INT` | `FK → users.id`, `INDEX` | 创建任务的用户 |
| `status` | `INT` | `NOT NULL`, `CHECK` | `1`=排队、`2`=执行、`3`=完成、`4`=部分完成、`5`=失败 |
| `created_at` / `started_at` / `finished_at` | `INT64` | - | 创建、开始及进入终态时间 |

### 7.12 `bidirectional_mtr_directions`

保存 `A_TO_B`、`B_TO_A` 两条独立方向任务的端点 IP 引用、租约和逐跳结果。

| 字段 | 数据类型 | 键 | 说明 |
| --- | --- | --- | --- |
| `id` | `INT` | `PK`, `AUTO_INCREMENT` | 方向任务内部主键 |
| `mtr_task_id` | `INT` | `FK → bidirectional_mtr_tasks.id` | 所属双向 MTR 主任务 |
| `direction` | `VARCHAR(8)` | `UNIQUE(mtr_task_id, direction)` | `A_TO_B` 或 `B_TO_A` |
| `source_ip_id` / `target_ip_id` | `INT` | - | 创建时选定的 IP 内部主键；地址和关联设备通过 `ip_dict` 查询，不建立外键 |
| `ip_version` | `INT` | `NOT NULL` | 地址族：`4` 或 `6` |
| `status` | `INT` | `NOT NULL`, `CHECK` | `1`=待领取、`2`=执行中、`3`=完成、`4`=部分完成、`5`=失败 |
| `lease_token` | `VARCHAR(64)` | - | 领取时签发的随机执行租约；上报结果必须匹配 |
| `result_data` | `JSON` | - | 每个 TTL 的地址、收发计数、丢包率及平均延迟 |
| `error_code` | `VARCHAR(64)` | - | 执行或端点校验失败原因 |
| `started_at` / `finished_at` | `INT64` | - | 方向领取和结束时间 |

任务领取与结果上报均通过 IP 主键关联 `ip_dict` 校验设备归属、公开状态和在线状态；关联 IP 不存在或失效时，方向任务不再下发。
