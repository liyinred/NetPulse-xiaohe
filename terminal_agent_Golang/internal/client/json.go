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
	"time"
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
//   - errorOutput: 接收非成功 HTTP 响应日志的 Writer。
//
// 返回值: 请求和解码成功时返回 nil，否则返回状态码或解析错误。
func executeJSONRequest(
	httpClient *http.Client,
	request *http.Request,
	destination any,
	errorOutput io.Writer,
) error {
	response, err := httpClient.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()

	body, readErr := io.ReadAll(io.LimitReader(response.Body, maxResponseSize))
	if readErr != nil {
		return fmt.Errorf("读取服务响应失败: %w", readErr)
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		logHTTPResponseError(errorOutput, request, response.StatusCode, body)
		return fmt.Errorf("服务返回 HTTP %d", response.StatusCode)
	}
	if err := json.NewDecoder(bytes.NewReader(body)).Decode(destination); err != nil {
		var networkError net.Error
		if errors.As(err, &networkError) {
			return fmt.Errorf("读取服务响应失败: %w", err)
		}
		return fmt.Errorf("解析服务响应失败: %w", err)
	}
	return nil
}

// logHTTPResponseError 记录非成功 HTTP 状态及受大小限制的原始响应内容。
//
// 参数:
//   - errorOutput: 接收接口错误信息的 Writer。
//   - request: 对应的 HTTP Request。
//   - statusCode: 服务返回的 HTTP 状态码。
//   - body: 最多一 MiB 的原始响应内容。
//
// 返回值: 无。
func logHTTPResponseError(
	errorOutput io.Writer,
	request *http.Request,
	statusCode int,
	body []byte,
) {
	beijingTime := time.Now().UTC().Add(8 * time.Hour).Format("2006-01-02 15:04:05")
	fmt.Fprintf(
		errorOutput,
		"北京时间=%s +08:00 HTTP 接口响应异常: method=%s url=%s status=%d response_body=%q\n",
		beijingTime,
		request.Method,
		request.URL.String(),
		statusCode,
		body,
	)
}
