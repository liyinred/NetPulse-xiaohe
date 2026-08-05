// Package client 提供 FastAPI 中央服务的 HTTP Client。
package client

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http"
	"net/netip"
	"net/url"
	"strings"
	"time"
)

const pollInterval = 2 * time.Second

var errQRCodeExpired = errors.New("二维码已过期")

// Backend 提供 FastAPI 中央服务访问能力。
type Backend struct {
	baseURL    string
	httpClient *http.Client
	ipv6Client *http.Client
}

// QRCode 保存微信登录二维码信息。
type QRCode struct {
	SceneString   string `json:"scene_str"`
	ExpireSeconds int    `json:"expire_seconds"`
	URL           string `json:"url"`
}

type qrCodeStatusResponse struct {
	Matched bool         `json:"matched"`
	Device  *BindingInfo `json:"device"`
}

type publicIPResponse struct {
	PublicIP string `json:"public_ip"`
}

type bindingStatusRequest struct {
	DeviceID   string  `json:"device_id"`
	SourceIPv4 string  `json:"source_ipv4"`
	SourceIPv6 *string `json:"source_ipv6"`
}

type bindingStatusResponse struct {
	Bound  bool         `json:"bound"`
	Device *BindingInfo `json:"device"`
}

// BindingInfo 保存中央服务确认绑定后的设备网络信息。
type BindingInfo struct {
	DeviceID     string  `json:"device_id"`
	PublicIPv4   string  `json:"public_ipv4"`
	PublicIPv6   *string `json:"public_ipv6"`
	ISP          int     `json:"isp"`
	Province     int     `json:"province"`
	City         string  `json:"city"`
	ISPName      string  `json:"isp_name"`
	ProvinceName string  `json:"province_name"`
}

// NewBackend 创建带请求超时的中央服务 Client。
//
// 参数:
//   - baseURL: FastAPI 后端基础 URL。
//   - timeout: 单次 HTTP 请求超时时间。
//
// 返回值: 可用于二维码登录和设备绑定轮询的 Backend。
func NewBackend(baseURL string, timeout time.Duration) *Backend {
	return &Backend{
		baseURL:    strings.TrimRight(baseURL, "/"),
		httpClient: newHTTPClient("tcp4", timeout),
		ipv6Client: newHTTPClient("tcp6", timeout),
	}
}

// newHTTPClient 创建强制使用指定 TCP 地址族的 HTTP Client。
//
// 参数:
//   - network: net.Dialer 使用的 tcp4 或 tcp6 网络类型。
//   - timeout: 单次 HTTP 请求超时时间。
//
// 返回值: 使用指定地址族建立连接的 HTTP Client。
func newHTTPClient(network string, timeout time.Duration) *http.Client {
	dialer := &net.Dialer{Timeout: timeout}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.DialContext = func(
		ctx context.Context,
		_ string,
		address string,
	) (net.Conn, error) {
		return dialer.DialContext(ctx, network, address)
	}
	return &http.Client{Timeout: timeout, Transport: transport}
}

// GetPublicIPv4 通过 IPv4 连接获取中央服务观察到的公网地址。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//
// 返回值: 有效公网 IPv4；请求或响应无效时返回错误。
func (backend *Backend) GetPublicIPv4(ctx context.Context) (netip.Addr, error) {
	return backend.getPublicIP(ctx, backend.httpClient, "/network/public-ipv4", 4)
}

// GetPublicIPv6 通过 IPv6 连接获取中央服务观察到的公网地址。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//
// 返回值: 有效公网 IPv6；请求或响应无效时返回错误。
func (backend *Backend) GetPublicIPv6(ctx context.Context) (netip.Addr, error) {
	return backend.getPublicIP(ctx, backend.ipv6Client, "/network/public-ipv6", 6)
}

// getPublicIP 请求并校验指定版本的公网地址。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - httpClient: 使用目标地址族的 HTTP Client。
//   - path: 中央服务公网地址接口路径。
//   - expectedVersion: 期望返回的 IP 版本。
//
// 返回值: 版本匹配的公网地址；请求或响应无效时返回错误。
func (backend *Backend) getPublicIP(
	ctx context.Context,
	httpClient *http.Client,
	path string,
	expectedVersion int,
) (netip.Addr, error) {
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		backend.baseURL+path,
		nil,
	)
	if err != nil {
		return netip.Addr{}, fmt.Errorf("创建公网 IPv%d 请求失败: %w", expectedVersion, err)
	}

	var response publicIPResponse
	if err := executeJSONRequest(httpClient, request, &response); err != nil {
		return netip.Addr{}, fmt.Errorf("获取公网 IPv%d 失败: %w", expectedVersion, err)
	}
	publicIP, err := netip.ParseAddr(response.PublicIP)
	if err != nil {
		return netip.Addr{}, fmt.Errorf("中央服务返回的公网 IPv%d 无效", expectedVersion)
	}
	if expectedVersion == 4 && !publicIP.Is4() ||
		expectedVersion == 6 && !publicIP.Is6() {
		return netip.Addr{}, fmt.Errorf("中央服务返回的公网 IPv%d 无效", expectedVersion)
	}
	return publicIP, nil
}

// CheckBinding 查询设备是否绑定有效关注用户，并刷新当前公网地址。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - deviceID: Agent 本地持久化的设备标识。
//   - sourceIPv4: 本次启动获取到的公网 IPv4。
//   - sourceIPv6: 本次启动获取到的公网 IPv6，未获取到时为空。
//
// 返回值: 已有效绑定时返回设备网络信息；未绑定时返回 nil；请求失败时返回错误。
func (backend *Backend) CheckBinding(
	ctx context.Context,
	deviceID string,
	sourceIPv4 netip.Addr,
	sourceIPv6 *netip.Addr,
) (*BindingInfo, error) {
	var sourceIPv6String *string
	if sourceIPv6 != nil {
		value := sourceIPv6.String()
		sourceIPv6String = &value
	}
	request, err := newJSONRequest(
		ctx,
		http.MethodPost,
		backend.baseURL+"/devices/binding-status",
		bindingStatusRequest{
			DeviceID:   deviceID,
			SourceIPv4: sourceIPv4.String(),
			SourceIPv6: sourceIPv6String,
		},
	)
	if err != nil {
		return nil, fmt.Errorf("创建绑定状态请求失败: %w", err)
	}

	var response bindingStatusResponse
	if err := executeJSONRequest(backend.httpClient, request, &response); err != nil {
		return nil, fmt.Errorf("查询绑定状态失败: %w", err)
	}
	if !response.Bound {
		return nil, nil
	}
	if response.Device == nil {
		return nil, errors.New("绑定状态响应缺少设备网络信息")
	}
	return response.Device, nil
}

// RequestQRCode 向 FastAPI 后端申请带场景值的微信二维码。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//
// 返回值: 二维码响应；请求或响应无效时返回错误。
func (backend *Backend) RequestQRCode(ctx context.Context) (QRCode, error) {
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		backend.baseURL+"/wechat/qrcode",
		nil,
	)
	if err != nil {
		return QRCode{}, fmt.Errorf("创建二维码请求失败: %w", err)
	}

	var response QRCode
	if err := executeJSONRequest(backend.httpClient, request, &response); err != nil {
		return QRCode{}, fmt.Errorf("申请二维码失败: %w", err)
	}
	if response.SceneString == "" || response.URL == "" || response.ExpireSeconds <= 0 {
		return QRCode{}, errors.New("二维码响应缺少有效字段")
	}
	return response, nil
}

// WaitForLogin 在二维码有效期内轮询并等待中央服务完成设备绑定。
//
// 参数:
//   - ctx: 控制轮询取消的 Context。
//   - sceneString: 二维码携带的 scene_str。
//   - deviceID: Agent 本地持久化的设备标识。
//   - sourceIPv4: 本次启动获取到的公网 IPv4。
//   - sourceIPv6: 本次启动获取到的公网 IPv6，未获取到时为空。
//   - validFor: 二维码剩余有效时间。
//
// 返回值: 绑定成功时返回设备网络信息；取消、过期或请求失败时返回错误。
func (backend *Backend) WaitForLogin(
	ctx context.Context,
	sceneString string,
	deviceID string,
	sourceIPv4 netip.Addr,
	sourceIPv6 *netip.Addr,
	validFor time.Duration,
) (BindingInfo, error) {
	deadline := time.NewTimer(validFor)
	defer deadline.Stop()
	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	for {
		bindingInfo, err := backend.checkLogin(
			ctx,
			sceneString,
			deviceID,
			sourceIPv4,
			sourceIPv6,
		)
		if err != nil {
			return BindingInfo{}, err
		}
		if bindingInfo != nil {
			return *bindingInfo, nil
		}

		select {
		case <-ctx.Done():
			return BindingInfo{}, ctx.Err()
		case <-deadline.C:
			return BindingInfo{}, errQRCodeExpired
		case <-ticker.C:
		}
	}
}

// checkLogin 查询指定 scene_str 是否已匹配，并由中央服务绑定 device_id。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - sceneString: 二维码携带的 scene_str。
//   - deviceID: Agent 本地持久化的设备标识。
//   - sourceIPv4: 本次启动获取到的公网 IPv4。
//   - sourceIPv6: 本次启动获取到的公网 IPv6，未获取到时为空。
//
// 返回值: 匹配成功时返回设备网络信息；尚未匹配时返回 nil；请求失败时返回错误。
func (backend *Backend) checkLogin(
	ctx context.Context,
	sceneString string,
	deviceID string,
	sourceIPv4 netip.Addr,
	sourceIPv6 *netip.Addr,
) (*BindingInfo, error) {
	endpoint, err := url.Parse(backend.baseURL + "/wechat/qrcode/status")
	if err != nil {
		return nil, fmt.Errorf("创建登录状态请求失败: %w", err)
	}
	query := endpoint.Query()
	query.Set("scene_str", sceneString)
	query.Set("device_id", deviceID)
	query.Set("source_ipv4", sourceIPv4.String())
	if sourceIPv6 != nil {
		query.Set("source_ipv6", sourceIPv6.String())
	}
	endpoint.RawQuery = query.Encode()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("创建登录状态请求失败: %w", err)
	}

	var response qrCodeStatusResponse
	if err := executeJSONRequest(backend.httpClient, request, &response); err != nil {
		return nil, fmt.Errorf("查询登录状态失败: %w", err)
	}
	if !response.Matched {
		return nil, nil
	}
	if response.Device == nil {
		return nil, errors.New("二维码状态响应缺少设备网络信息")
	}
	return response.Device, nil
}
