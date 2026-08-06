package client

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
)

const maxResponseSize = 1 << 20

// newJSONRequest 创建包含 JSON 请求体的 HTTP Request。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - method: HTTP 请求方法。
//   - endpoint: 完整请求地址。
//   - payload: 要编码的结构化请求数据。
//
// 返回值: 已设置 Content-Type 的请求；编码或创建失败时返回错误。
func newJSONRequest(
	ctx context.Context,
	method string,
	endpoint string,
	payload any,
) (*http.Request, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("编码 JSON 请求失败: %w", err)
	}
	request, err := http.NewRequestWithContext(
		ctx,
		method,
		endpoint,
		bytes.NewReader(body),
	)
	if err != nil {
		return nil, errors.New("请求地址无效")
	}
	request.Header.Set("Content-Type", "application/json")
	return request, nil
}

// executeJSONRequest 执行 HTTP 请求并解析受大小限制的 JSON 响应。
//
// 参数:
//   - httpClient: 用于执行请求的 HTTP Client。
//   - request: 已构造完成的 HTTP Request。
//   - destination: 接收 JSON 解码结果的目标值。
//
// 返回值: 请求和解码成功时返回 nil，否则返回状态码或解析错误。
func executeJSONRequest(
	httpClient *http.Client,
	request *http.Request,
	destination any,
) error {
	response, err := httpClient.Do(request)
	if err != nil {
		return safeRequestError(err)
	}
	defer response.Body.Close()

	limitedBody := io.LimitReader(response.Body, maxResponseSize)
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return fmt.Errorf("服务返回 HTTP %d", response.StatusCode)
	}
	if err := json.NewDecoder(limitedBody).Decode(destination); err != nil {
		var networkError net.Error
		if errors.As(err, &networkError) {
			return fmt.Errorf("读取服务响应失败: %w", safeRequestError(err))
		}
		return fmt.Errorf("解析服务响应失败: %w", err)
	}
	return nil
}

// safeRequestError 将 HTTP 请求错误转换为不包含真实接口地址的终端错误。
//
// 参数:
//   - err: http.Client 执行请求时返回的原始错误。
//
// 返回值: 仅描述取消、超时或连接失败类型的安全错误。
func safeRequestError(err error) error {
	switch {
	case errors.Is(err, context.Canceled):
		return errors.New("请求已取消")
	case errors.Is(err, context.DeadlineExceeded):
		return errors.New("请求超时")
	}
	var networkError net.Error
	if errors.As(err, &networkError) && networkError.Timeout() {
		return errors.New("请求超时")
	}
	return errors.New("网络连接失败")
}
