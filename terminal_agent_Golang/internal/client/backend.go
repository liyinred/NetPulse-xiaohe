// Package client 提供中央服务和公网网络信息的 HTTP Client。
package client

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
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
}

// QRCode 保存微信登录二维码信息。
type QRCode struct {
	SceneString   string `json:"scene_str"`
	ExpireSeconds int    `json:"expire_seconds"`
	URL           string `json:"url"`
}

// DeviceBinding 保存需要提交到中央服务的设备信息。
type DeviceBinding struct {
	DeviceID   string `json:"device_id"`
	OpenID     string `json:"openid"`
	PublicIPv4 string `json:"public_ipv4"`
	ISP        int    `json:"isp"`
	Province   int    `json:"province"`
}

type qrCodeStatusResponse struct {
	Matched bool   `json:"matched"`
	OpenID  string `json:"openid"`
}

type deviceBindResponse struct {
	ID         int64  `json:"id"`
	DeviceID   string `json:"device_id"`
	PublicIPv4 string `json:"public_ipv4"`
	ISP        int    `json:"isp"`
	Province   int    `json:"province"`
}

// NewBackend 创建带请求超时的中央服务 Client。
//
// 参数:
//   - baseURL: FastAPI 后端基础 URL。
//   - timeout: 单次 HTTP 请求超时时间。
//
// 返回值: 可用于登录和设备绑定的 Backend。
func NewBackend(baseURL string, timeout time.Duration) *Backend {
	return &Backend{
		baseURL:    strings.TrimRight(baseURL, "/"),
		httpClient: &http.Client{Timeout: timeout},
	}
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

// WaitForLogin 在二维码有效期内轮询场景值对应的登录状态。
//
// 参数:
//   - ctx: 控制轮询取消的 Context。
//   - sceneString: 二维码携带的 scene_str。
//   - validFor: 二维码剩余有效时间。
//
// 返回值: 匹配用户的 openid；取消、过期或请求失败时返回错误。
func (backend *Backend) WaitForLogin(
	ctx context.Context,
	sceneString string,
	validFor time.Duration,
) (string, error) {
	deadline := time.NewTimer(validFor)
	defer deadline.Stop()
	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	for {
		matched, openID, err := backend.checkLogin(ctx, sceneString)
		if err != nil {
			return "", err
		}
		if matched {
			return openID, nil
		}

		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-deadline.C:
			return "", errQRCodeExpired
		case <-ticker.C:
		}
	}
}

// BindDevice 将登录用户、设备标识及归一化网络属性提交到 FastAPI 后端绑定。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - binding: 要提交的设备绑定信息。
//
// 返回值: 绑定成功时返回 nil，否则返回请求或响应错误。
func (backend *Backend) BindDevice(ctx context.Context, binding DeviceBinding) error {
	payload, err := json.Marshal(binding)
	if err != nil {
		return fmt.Errorf("序列化设备绑定请求失败: %w", err)
	}
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		backend.baseURL+"/devices/bind",
		bytes.NewReader(payload),
	)
	if err != nil {
		return fmt.Errorf("创建设备绑定请求失败: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")

	var response deviceBindResponse
	if err := executeJSONRequest(backend.httpClient, request, &response); err != nil {
		return fmt.Errorf("绑定设备失败: %w", err)
	}
	if response.ID <= 0 ||
		response.DeviceID != binding.DeviceID ||
		response.PublicIPv4 != binding.PublicIPv4 ||
		response.ISP != binding.ISP ||
		response.Province != binding.Province {
		return errors.New("设备绑定响应与请求不一致")
	}
	return nil
}

// checkLogin 查询指定 scene_str 是否已匹配有效用户。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - sceneString: 二维码携带的 scene_str。
//
// 返回值: 是否匹配、匹配用户的 openid，以及请求错误。
func (backend *Backend) checkLogin(
	ctx context.Context,
	sceneString string,
) (bool, string, error) {
	endpoint, err := url.Parse(backend.baseURL + "/wechat/qrcode/status")
	if err != nil {
		return false, "", fmt.Errorf("创建登录状态请求失败: %w", err)
	}
	query := endpoint.Query()
	query.Set("scene_str", sceneString)
	endpoint.RawQuery = query.Encode()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return false, "", fmt.Errorf("创建登录状态请求失败: %w", err)
	}

	var response qrCodeStatusResponse
	if err := executeJSONRequest(backend.httpClient, request, &response); err != nil {
		return false, "", fmt.Errorf("查询登录状态失败: %w", err)
	}
	if response.Matched && response.OpenID == "" {
		return false, "", errors.New("登录状态响应缺少 openid")
	}
	return response.Matched, response.OpenID, nil
}
