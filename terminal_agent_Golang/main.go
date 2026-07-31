package main

import (
	"bytes"
	"context"
	"crypto/rand"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"syscall"
	"time"

	qrcode "github.com/skip2/go-qrcode"
	"gopkg.in/yaml.v3"
)

const (
	configFileName       = "config.yaml"
	legacyConfigFileName = "config.json"
	backendBaseURL       = "http://175.4.50.59:8086"
	publicIPEndpoint     = "https://api.ip.sb/ip"
	pollInterval         = 2 * time.Second
	requestTimeout       = 10 * time.Second
	maxResponseSize      = 1 << 20
	maxIPAddressSize     = 64
)

var errQRCodeExpired = errors.New("二维码已过期")

type config struct {
	Device deviceConfig `yaml:"device"`
	User   userConfig   `yaml:"user"`
}

type quotedString string

type deviceConfig struct {
	DeviceID   quotedString `yaml:"device_id"`
	PublicIPv4 quotedString `yaml:"public_ipv4"`
}

type userConfig struct {
	OpenID quotedString `yaml:"openid"`
}

type legacyConfig struct {
	OpenID     string `json:"openid"`
	DeviceID   string `json:"device_id"`
	PublicIPv4 string `json:"public_ipv4"`
}

type qrCodeResponse struct {
	SceneString   string `json:"scene_str"`
	ExpireSeconds int    `json:"expire_seconds"`
	URL           string `json:"url"`
}

type qrCodeStatusResponse struct {
	Matched bool   `json:"matched"`
	OpenID  string `json:"openid"`
}

type deviceBindRequest struct {
	DeviceID   string `json:"device_id"`
	OpenID     string `json:"openid"`
	PublicIPv4 string `json:"public_ipv4"`
}

type deviceBindResponse struct {
	ID         int64  `json:"id"`
	DeviceID   string `json:"device_id"`
	PublicIPv4 string `json:"public_ipv4"`
}

// main 初始化 Agent，并在收到退出信号时取消当前运行流程。
//
// 参数: 无。
// 返回值: 无。
func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if err := run(ctx, os.Stdout); err != nil {
		fmt.Fprintf(os.Stderr, "Agent 运行失败: %v\n", err)
		os.Exit(1)
	}
}

// run 执行登录、公网 IPv4 获取、设备标识持久化与后端绑定流程。
//
// 参数:
//   - ctx: 控制 Agent 退出的 Context。
//   - output: 输出二维码和运行状态的 Writer。
//
// 返回值: 流程成功时返回 nil，否则返回具体错误。
func run(ctx context.Context, output io.Writer) error {
	configPath, err := executableConfigPath()
	if err != nil {
		return err
	}

	agentConfig, created, err := loadOrCreateConfig(configPath)
	if err != nil {
		return err
	}
	if created {
		fmt.Fprintf(output, "已创建配置文件: %s\n", configPath)
	}

	client := &http.Client{Timeout: requestTimeout}
	publicIPTransport := http.DefaultTransport.(*http.Transport).Clone()
	publicIPTransport.DialContext = dialIPv4
	defer publicIPTransport.CloseIdleConnections()
	publicIPClient := &http.Client{Timeout: requestTimeout, Transport: publicIPTransport}
	qrCode, err := requestQRCode(ctx, client, backendBaseURL)
	if err != nil {
		return err
	}
	if err := printQRCode(output, qrCode.URL); err != nil {
		return err
	}

	fmt.Fprintln(output, "请使用微信扫描二维码完成登录，正在等待确认...")
	openid, err := waitForLogin(
		ctx,
		client,
		backendBaseURL,
		qrCode.SceneString,
		time.Duration(qrCode.ExpireSeconds)*time.Second,
	)
	if err != nil {
		return err
	}

	publicIPv4, err := requestPublicIPv4(ctx, publicIPClient)
	if err != nil {
		return err
	}
	deviceID := strings.TrimSpace(string(agentConfig.Device.DeviceID))
	if deviceID == "" {
		deviceID, err = generateDeviceID()
		if err != nil {
			return err
		}
	}

	agentConfig.User.OpenID = quotedString(openid)
	agentConfig.Device.DeviceID = quotedString(deviceID)
	agentConfig.Device.PublicIPv4 = quotedString(publicIPv4)
	if err := writeConfig(configPath, agentConfig); err != nil {
		return err
	}
	if err := bindDevice(ctx, client, backendBaseURL, deviceBindRequest{
		DeviceID:   deviceID,
		OpenID:     openid,
		PublicIPv4: publicIPv4,
	}); err != nil {
		return err
	}
	fmt.Fprintln(output, "登录成功，设备信息已保存并完成绑定。")
	return nil
}

// executableConfigPath 返回可执行文件同目录下的配置文件路径。
//
// 参数: 无。
// 返回值: 配置文件绝对路径；无法确定可执行文件位置时返回错误。
func executableConfigPath() (string, error) {
	executablePath, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("获取 Agent 程序路径失败: %w", err)
	}
	resolvedPath, err := filepath.EvalSymlinks(executablePath)
	if err != nil {
		resolvedPath = executablePath
	}
	return filepath.Join(filepath.Dir(resolvedPath), configFileName), nil
}

// loadOrCreateConfig 读取 YAML 配置文件，并在文件不存在时创建空配置。
//
// 参数:
//   - path: 配置文件路径。
//
// 返回值: 配置内容、是否新建配置文件以及处理错误。
func loadOrCreateConfig(path string) (config, bool, error) {
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		legacyPath := filepath.Join(filepath.Dir(path), legacyConfigFileName)
		legacy, found, legacyErr := loadLegacyConfig(legacyPath)
		if legacyErr != nil {
			return config{}, false, legacyErr
		}
		if found {
			migratedConfig := config{
				Device: deviceConfig{
					DeviceID:   quotedString(legacy.DeviceID),
					PublicIPv4: quotedString(legacy.PublicIPv4),
				},
				User: userConfig{OpenID: quotedString(legacy.OpenID)},
			}
			if writeErr := writeConfig(path, migratedConfig); writeErr != nil {
				return config{}, false, writeErr
			}
			return migratedConfig, true, nil
		}

		defaultConfig := config{}
		if writeErr := writeConfig(path, defaultConfig); writeErr != nil {
			return config{}, false, writeErr
		}
		return defaultConfig, true, nil
	}
	if err != nil {
		return config{}, false, fmt.Errorf("读取配置文件失败: %w", err)
	}

	var agentConfig config
	if err := yaml.Unmarshal(data, &agentConfig); err != nil {
		return config{}, false, fmt.Errorf("解析配置文件失败: %w", err)
	}
	return agentConfig, false, nil
}

// loadLegacyConfig 读取旧版扁平 JSON 配置以迁移设备和用户标识。
//
// 参数:
//   - path: 旧版 config.json 文件路径。
//
// 返回值: 旧版配置、文件是否存在以及读取或解析错误。
func loadLegacyConfig(path string) (legacyConfig, bool, error) {
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return legacyConfig{}, false, nil
	}
	if err != nil {
		return legacyConfig{}, false, fmt.Errorf("读取旧版配置文件失败: %w", err)
	}

	var legacy legacyConfig
	if err := json.Unmarshal(data, &legacy); err != nil {
		return legacyConfig{}, false, fmt.Errorf("解析旧版配置文件失败: %w", err)
	}
	return legacy, true, nil
}

// MarshalYAML 将配置字符串编码为带双引号的 YAML 标量。
//
// 参数: 无。
// 返回值: 使用双引号样式的 YAML Node，以及始终为 nil 的错误。
func (value quotedString) MarshalYAML() (any, error) {
	return &yaml.Node{
		Kind:  yaml.ScalarNode,
		Tag:   "!!str",
		Value: string(value),
		Style: yaml.DoubleQuotedStyle,
	}, nil
}

// writeConfig 将 Agent 配置以 YAML 格式写入指定文件。
//
// 参数:
//   - path: 配置文件路径。
//   - agentConfig: 要保存的配置内容。
//
// 返回值: 保存成功时返回 nil，否则返回写入错误。
func writeConfig(path string, agentConfig config) error {
	var buffer bytes.Buffer
	encoder := yaml.NewEncoder(&buffer)
	encoder.SetIndent(2)
	if err := encoder.Encode(agentConfig); err != nil {
		return fmt.Errorf("序列化配置文件失败: %w", err)
	}
	if err := encoder.Close(); err != nil {
		return fmt.Errorf("关闭 YAML Encoder 失败: %w", err)
	}
	if err := os.WriteFile(path, buffer.Bytes(), 0o600); err != nil {
		return fmt.Errorf("写入配置文件失败: %w", err)
	}
	return nil
}

// requestQRCode 向 FastAPI 后端申请带场景值的微信二维码。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - client: 用于访问后端的 HTTP Client。
//   - backendURL: FastAPI 后端基础 URL。
//
// 返回值: 二维码响应；请求或响应无效时返回错误。
func requestQRCode(
	ctx context.Context,
	client *http.Client,
	backendURL string,
) (qrCodeResponse, error) {
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		backendURL+"/wechat/qrcode",
		nil,
	)
	if err != nil {
		return qrCodeResponse{}, fmt.Errorf("创建二维码请求失败: %w", err)
	}

	var response qrCodeResponse
	if err := executeJSONRequest(client, request, &response); err != nil {
		return qrCodeResponse{}, fmt.Errorf("申请二维码失败: %w", err)
	}
	if response.SceneString == "" || response.URL == "" || response.ExpireSeconds <= 0 {
		return qrCodeResponse{}, errors.New("二维码响应缺少有效字段")
	}
	return response, nil
}

// printQRCode 将二维码 URL 编码为适合终端展示的紧凑字符图形。
//
// 参数:
//   - output: 接收终端二维码的 Writer。
//   - content: 后端二维码响应中的微信访问 URL。
//
// 返回值: 二维码生成成功时返回 nil，否则返回编码错误。
func printQRCode(output io.Writer, content string) error {
	code, err := qrcode.New(content, qrcode.Medium)
	if err != nil {
		return fmt.Errorf("生成终端二维码失败: %w", err)
	}
	if _, err := fmt.Fprint(output, code.ToSmallString(false)); err != nil {
		return fmt.Errorf("输出终端二维码失败: %w", err)
	}
	return nil
}

// dialIPv4 强制使用 TCP over IPv4 建立网络连接。
//
// 参数:
//   - ctx: 控制连接取消和超时的 Context。
//   - network: HTTP Transport 提供的网络类型，本函数固定使用 tcp4。
//   - address: 要连接的主机和端口。
//
// 返回值: 建立的网络连接；连接失败时返回错误。
func dialIPv4(ctx context.Context, network string, address string) (net.Conn, error) {
	dialer := &net.Dialer{}
	return dialer.DialContext(ctx, "tcp4", address)
}

// requestPublicIPv4 从公网查询并校验当前设备的 IPv4 地址。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - client: 用于访问公网服务的 HTTP Client。
//
// 返回值: 规范化的公网 IPv4 地址；请求或响应无效时返回错误。
func requestPublicIPv4(ctx context.Context, client *http.Client) (string, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, publicIPEndpoint, nil)
	if err != nil {
		return "", fmt.Errorf("创建公网 IPv4 请求失败: %w", err)
	}

	response, err := client.Do(request)
	if err != nil {
		return "", fmt.Errorf("获取公网 IPv4 失败: %w", err)
	}
	defer response.Body.Close()

	body, err := io.ReadAll(io.LimitReader(response.Body, maxIPAddressSize+1))
	if err != nil {
		return "", fmt.Errorf("读取公网 IPv4 响应失败: %w", err)
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return "", fmt.Errorf(
			"公网 IPv4 服务返回 HTTP %d: %s",
			response.StatusCode,
			strings.TrimSpace(string(body)),
		)
	}
	if len(body) > maxIPAddressSize {
		return "", errors.New("公网 IPv4 响应过大")
	}

	ipAddress := net.ParseIP(strings.TrimSpace(string(body)))
	if ipAddress == nil || ipAddress.To4() == nil {
		return "", errors.New("公网 IPv4 服务未返回有效的 IPv4 地址")
	}
	return ipAddress.To4().String(), nil
}

// generateDeviceID 使用加密安全随机数生成 UUID v4 设备标识。
//
// 参数: 无。
// 返回值: UUID v4 字符串；随机数读取失败时返回错误。
func generateDeviceID() (string, error) {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		return "", fmt.Errorf("生成 device_id 失败: %w", err)
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf(
		"%x-%x-%x-%x-%x",
		value[0:4],
		value[4:6],
		value[6:8],
		value[8:10],
		value[10:16],
	), nil
}

// bindDevice 将登录用户、设备标识和公网 IPv4 提交到 FastAPI 后端绑定。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - client: 用于访问后端的 HTTP Client。
//   - backendURL: FastAPI 后端基础 URL。
//   - binding: 要提交的设备绑定信息。
//
// 返回值: 绑定成功时返回 nil，否则返回请求或响应错误。
func bindDevice(
	ctx context.Context,
	client *http.Client,
	backendURL string,
	binding deviceBindRequest,
) error {
	payload, err := json.Marshal(binding)
	if err != nil {
		return fmt.Errorf("序列化设备绑定请求失败: %w", err)
	}
	request, err := http.NewRequestWithContext(
		ctx,
		http.MethodPost,
		backendURL+"/devices/bind",
		bytes.NewReader(payload),
	)
	if err != nil {
		return fmt.Errorf("创建设备绑定请求失败: %w", err)
	}
	request.Header.Set("Content-Type", "application/json")

	var response deviceBindResponse
	if err := executeJSONRequest(client, request, &response); err != nil {
		return fmt.Errorf("绑定设备失败: %w", err)
	}
	if response.ID <= 0 || response.DeviceID != binding.DeviceID || response.PublicIPv4 != binding.PublicIPv4 {
		return errors.New("设备绑定响应与请求不一致")
	}
	return nil
}

// waitForLogin 在二维码有效期内轮询 scene_str 对应的登录状态。
//
// 参数:
//   - ctx: 控制轮询取消的 Context。
//   - client: 用于访问后端的 HTTP Client。
//   - backendURL: FastAPI 后端基础 URL。
//   - sceneString: 二维码携带的场景值。
//   - validFor: 二维码剩余有效时间。
//
// 返回值: 匹配用户的 openid；取消、过期或请求失败时返回错误。
func waitForLogin(
	ctx context.Context,
	client *http.Client,
	backendURL string,
	sceneString string,
	validFor time.Duration,
) (string, error) {
	deadline := time.NewTimer(validFor)
	defer deadline.Stop()
	ticker := time.NewTicker(pollInterval)
	defer ticker.Stop()

	for {
		matched, openid, err := checkLogin(ctx, client, backendURL, sceneString)
		if err != nil {
			return "", err
		}
		if matched {
			return openid, nil
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

// checkLogin 查询指定 scene_str 是否已匹配有效用户。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - client: 用于访问后端的 HTTP Client。
//   - backendURL: FastAPI 后端基础 URL。
//   - sceneString: 二维码携带的场景值。
//
// 返回值: 是否匹配、匹配用户的 openid，以及请求错误。
func checkLogin(
	ctx context.Context,
	client *http.Client,
	backendURL string,
	sceneString string,
) (bool, string, error) {
	endpoint, err := url.Parse(backendURL + "/wechat/qrcode/status")
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
	if err := executeJSONRequest(client, request, &response); err != nil {
		return false, "", fmt.Errorf("查询登录状态失败: %w", err)
	}
	if response.Matched && response.OpenID == "" {
		return false, "", errors.New("登录状态响应缺少 openid")
	}
	return response.Matched, response.OpenID, nil
}

// executeJSONRequest 执行 HTTP 请求并解析受大小限制的 JSON 响应。
//
// 参数:
//   - client: 用于执行请求的 HTTP Client。
//   - request: 已构造完成的 HTTP Request。
//   - destination: 接收 JSON 解码结果的目标值。
//
// 返回值: 请求和解码成功时返回 nil，否则返回状态码或解析错误。
func executeJSONRequest(
	client *http.Client,
	request *http.Request,
	destination any,
) error {
	response, err := client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()

	limitedBody := io.LimitReader(response.Body, maxResponseSize)
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		body, _ := io.ReadAll(limitedBody)
		return fmt.Errorf("后端返回 HTTP %d: %s", response.StatusCode, strings.TrimSpace(string(body)))
	}
	if err := json.NewDecoder(limitedBody).Decode(destination); err != nil {
		return fmt.Errorf("解析后端响应失败: %w", err)
	}
	return nil
}
