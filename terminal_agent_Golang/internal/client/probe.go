package client

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/netip"
	"net/url"
)

// ProbeTarget 保存中央服务下发的单个探测目标。
type ProbeTarget struct {
	PublicIP string `json:"public_ip"`
	ISP      int    `json:"isp"`
	Province int    `json:"province"`
}

// ProbeTargets 保存按分类和 IP 版本拆分的持续探测目标。
type ProbeTargets struct {
	SourceIPv4               string        `json:"source_ipv4"`
	SourceIPv6               *string       `json:"source_ipv6"`
	CrossISPIPv4Targets      []ProbeTarget `json:"cross_isp_ipv4_targets"`
	CrossProvinceIPv4Targets []ProbeTarget `json:"cross_province_ipv4_targets"`
	CrossISPIPv6Targets      []ProbeTarget `json:"cross_isp_ipv6_targets"`
	CrossProvinceIPv6Targets []ProbeTarget `json:"cross_province_ipv6_targets"`
}

type probeTargetsRequest struct {
	DeviceID   string  `json:"device_id"`
	SourceIPv4 string  `json:"source_ipv4"`
	SourceIPv6 *string `json:"source_ipv6"`
}

// ProtocolResult 保存一种协议的分钟汇总结果。
type ProtocolResult struct {
	LossRate         int `json:"loss_rate"`
	AverageLatencyMS int `json:"average_latency_ms"`
}

// TargetResult 保存一个目标的三种协议分钟汇总结果。
type TargetResult struct {
	TargetIP string         `json:"target_ip"`
	ICMP     ProtocolResult `json:"icmp"`
	TCP      ProtocolResult `json:"tcp"`
	UDP      ProtocolResult `json:"udp"`
}

// ProbeResultRequest 保存一个分类、IP 版本和源地址的分钟结果。
type ProbeResultRequest struct {
	DeviceID      string         `json:"device_id"`
	ProbeMode     string         `json:"probe_mode"`
	IPVersion     int            `json:"ip_version"`
	SourceIP      string         `json:"source_ip"`
	UnixTimestamp int64          `json:"unix_timestamp"`
	Targets       []TargetResult `json:"targets"`
}

// ProbeAlertRequest 保存一个目标和协议的分钟丢包告警。
type ProbeAlertRequest struct {
	EventID       string `json:"event_id"`
	DeviceID      string `json:"device_id"`
	ProbeMode     string `json:"probe_mode"`
	IPVersion     int    `json:"ip_version"`
	SourceIP      string `json:"source_ip"`
	TargetIP      string `json:"target_ip"`
	ProtocolType  string `json:"protocol_type"`
	LossRate      int    `json:"loss_rate"`
	UnixTimestamp int64  `json:"unix_timestamp"`
}

// ProbeAlertsRequest 保存一个自然分钟内的聚合丢包告警。
type ProbeAlertsRequest struct {
	Alerts []ProbeAlertRequest `json:"alerts"`
}

type probeAcceptedResponse struct {
	Accepted bool `json:"accepted"`
}

// OnDemandTask 保存中央服务下发的临时 IP 按需探测任务。
type OnDemandTask struct {
	ID         int64  `json:"id"`
	SourceIP   string `json:"source_ip"`
	TargetIP   string `json:"target_ip"`
	IPVersion  int    `json:"ip_version"`
	ProbeCount int    `json:"probe_count"`
	IntervalMS int    `json:"interval_ms"`
	TimeoutMS  int    `json:"timeout_ms"`
}

type onDemandTaskResponse struct {
	Data *OnDemandTask `json:"data"`
}

// OnDemandResults 保存按需任务的三协议汇总结果。
type OnDemandResults struct {
	ICMP ProtocolResult `json:"icmp"`
	TCP  ProtocolResult `json:"tcp"`
	UDP  ProtocolResult `json:"udp"`
}

// OnDemandResultRequest 保存节点任务的完整按需探测上报。
type OnDemandResultRequest struct {
	TaskID     int64           `json:"task_id"`
	DeviceID   string          `json:"device_id"`
	SourceIP   string          `json:"source_ip"`
	TargetIP   string          `json:"target_ip"`
	StartedAt  int64           `json:"started_at"`
	FinishedAt int64           `json:"finished_at"`
	Results    OnDemandResults `json:"results"`
}

// FetchProbeTargets 使用当前公网地址查询异网和跨省目标。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - deviceID: Agent 设备标识。
//   - sourceIPv4: 当前公网 IPv4。
//   - sourceIPv6: 当前公网 IPv6，未获取到时为空。
//
// 返回值: 中央服务下发的分类目标；请求或响应无效时返回错误。
func (backend *Backend) FetchProbeTargets(
	ctx context.Context,
	deviceID string,
	sourceIPv4 netip.Addr,
	sourceIPv6 *netip.Addr,
) (ProbeTargets, error) {
	var sourceIPv6String *string
	if sourceIPv6 != nil {
		value := sourceIPv6.String()
		sourceIPv6String = &value
	}
	request, err := newJSONRequest(
		ctx,
		http.MethodPost,
		backend.baseURL+"/probes/targets",
		probeTargetsRequest{
			DeviceID:   deviceID,
			SourceIPv4: sourceIPv4.String(),
			SourceIPv6: sourceIPv6String,
		},
	)
	if err != nil {
		return ProbeTargets{}, fmt.Errorf("创建探测目标请求失败: %w", err)
	}
	var response ProbeTargets
	if err := executeJSONRequest(backend.httpClient, request, &response); err != nil {
		return ProbeTargets{}, fmt.Errorf("查询探测目标失败: %w", err)
	}
	return response, nil
}

// SubmitProbeResult 上报一个分类的自然分钟探测结果。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - result: 完整分钟结果。
//
// 返回值: 中央服务接受请求时返回 nil，否则返回错误。
func (backend *Backend) SubmitProbeResult(
	ctx context.Context,
	result ProbeResultRequest,
) error {
	return backend.submitProbePayload(ctx, "/probes/results", result)
}

// SubmitProbeAlerts 上报一个自然分钟内的聚合丢包告警。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - alerts: 当前自然分钟的聚合丢包告警。
//
// 返回值: 中央服务接受请求时返回 nil，否则返回错误。
func (backend *Backend) SubmitProbeAlerts(
	ctx context.Context,
	alerts ProbeAlertsRequest,
) error {
	return backend.submitProbePayload(ctx, "/probes/alerts", alerts)
}

// PollOnDemandTask 长轮询并领取当前设备的一个按需探测任务。
//
// 参数:
//   - ctx: 控制长轮询取消的 Context。
//   - deviceID: Agent 设备标识。
//
// 返回值: 领取到的任务；无任务时返回 nil，请求失败时返回错误。
func (backend *Backend) PollOnDemandTask(
	ctx context.Context,
	deviceID string,
) (*OnDemandTask, error) {
	endpoint := backend.baseURL + "/probes/on-demand/tasks?device_id=" + url.QueryEscape(deviceID)
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, nil)
	if err != nil {
		return nil, fmt.Errorf("创建按需任务轮询请求失败: %w", err)
	}
	var response onDemandTaskResponse
	if err := executeJSONRequest(backend.httpClient, request, &response); err != nil {
		return nil, fmt.Errorf("轮询按需探测任务失败: %w", err)
	}
	return response.Data, nil
}

// SubmitOnDemandResult 幂等上报一个节点任务的三协议结果。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - result: 节点任务及其完整探测结果。
//
// 返回值: 中央服务接受请求时返回 nil，否则返回错误。
func (backend *Backend) SubmitOnDemandResult(
	ctx context.Context,
	result OnDemandResultRequest,
) error {
	return backend.submitProbePayload(ctx, "/probes/on-demand/results", result)
}

// submitProbePayload 提交探测 JSON 并校验接受标志。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - path: 中央服务探测接口路径。
//   - payload: 结果或告警请求体。
//
// 返回值: 请求被中央服务接受时返回 nil，否则返回错误。
func (backend *Backend) submitProbePayload(
	ctx context.Context,
	path string,
	payload any,
) error {
	request, err := newJSONRequest(
		ctx,
		http.MethodPost,
		backend.baseURL+path,
		payload,
	)
	if err != nil {
		return fmt.Errorf("创建探测上报请求失败: %w", err)
	}
	var response probeAcceptedResponse
	if err := executeJSONRequest(backend.httpClient, request, &response); err != nil {
		return fmt.Errorf("提交探测上报失败: %w", err)
	}
	if !response.Accepted {
		return errors.New("中央服务未接受探测上报")
	}
	return nil
}
