package client

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/netip"
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

// ProbeAlertRequest 保存一次探测丢包事件。
type ProbeAlertRequest struct {
	EventID       string `json:"event_id"`
	DeviceID      string `json:"device_id"`
	ProbeMode     string `json:"probe_mode"`
	IPVersion     int    `json:"ip_version"`
	SourceIP      string `json:"source_ip"`
	TargetIP      string `json:"target_ip"`
	ProtocolType  string `json:"protocol_type"`
	UnixTimestamp int64  `json:"unix_timestamp"`
}

type probeAcceptedResponse struct {
	Accepted bool `json:"accepted"`
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

// SubmitProbeAlert 上报一次探测丢包事件。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - alert: 单次丢包事件。
//
// 返回值: 中央服务接受请求时返回 nil，否则返回错误。
func (backend *Backend) SubmitProbeAlert(
	ctx context.Context,
	alert ProbeAlertRequest,
) error {
	return backend.submitProbePayload(ctx, "/probes/alerts", alert)
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
