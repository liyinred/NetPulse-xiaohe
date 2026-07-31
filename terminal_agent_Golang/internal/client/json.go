package client

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
)

const maxResponseSize = 1 << 20

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
		return err
	}
	defer response.Body.Close()

	limitedBody := io.LimitReader(response.Body, maxResponseSize)
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		body, _ := io.ReadAll(limitedBody)
		return fmt.Errorf("服务返回 HTTP %d: %s", response.StatusCode, strings.TrimSpace(string(body)))
	}
	if err := json.NewDecoder(limitedBody).Decode(destination); err != nil {
		return fmt.Errorf("解析服务响应失败: %w", err)
	}
	return nil
}
