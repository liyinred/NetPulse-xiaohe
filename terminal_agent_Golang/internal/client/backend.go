// Package client 提供 FastAPI 中央服务的 HTTP Client。
package client

import (
	"context"
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

type qrCodeStatusResponse struct {
	Matched bool `json:"matched"`
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

// WaitForLogin 在二维码有效期内轮询并等待中央服务完成设备绑定。
//
// 参数:
//   - ctx: 控制轮询取消的 Context。
//   - sceneString: 二维码携带的 scene_str。
//   - deviceID: Agent 本地持久化的设备标识。
//   - validFor: 二维码剩余有效时间。
//
// 返回值: 绑定成功时返回 nil；取消、过期或请求失败时返回错误。
func (backend *Backend) WaitForLogin(
	ctx context.Context,
	sceneString string,
	deviceID string,
	validFor time.Duration,
) error {
	deadline := time.NewTimer(validFor)
	defer deadline.Stop()
	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	for {
		matched, err := backend.checkLogin(ctx, sceneString, deviceID)
		if err != nil {
			return err
		}
		if matched {
			return nil
		}

		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-deadline.C:
			return errQRCodeExpired
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
//
// 返回值: 是否完成设备绑定，以及请求错误。
func (backend *Backend) checkLogin(
	ctx context.Context,
	sceneString string,
	deviceID string,
) (bool, error) {
	endpoint, err := url.Parse(backend.baseURL + "/wechat/qrcode/status")
	if err != nil {
		return false, fmt.Errorf("创建登录状态请求失败: %w", err)
	}
	query := endpoint.Query()
	query.Set("scene_str", sceneString)
	query.Set("device_id", deviceID)
	endpoint.RawQuery = query.Encode()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return false, fmt.Errorf("创建登录状态请求失败: %w", err)
	}

	var response qrCodeStatusResponse
	if err := executeJSONRequest(backend.httpClient, request, &response); err != nil {
		return false, fmt.Errorf("查询登录状态失败: %w", err)
	}
	return response.Matched, nil
}
