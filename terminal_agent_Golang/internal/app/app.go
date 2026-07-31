// Package app 编排 Agent 的登录、网络查询和设备绑定流程。
package app

import (
	"context"
	"crypto/rand"
	"fmt"
	"io"
	"time"

	"netpulse/terminal-agent/internal/client"
	"netpulse/terminal-agent/internal/config"

	qrcode "github.com/skip2/go-qrcode"
)

const (
	backendBaseURL = "http://175.4.50.59:8086"
	requestTimeout = 10 * time.Second
)

// Run 执行登录、公网 IPv4 与归属信息获取、设备标识持久化及后端绑定流程。
//
// 参数:
//   - ctx: 控制 Agent 退出的 Context。
//   - output: 输出二维码和运行状态的 Writer。
//
// 返回值: 流程成功时返回 nil，否则返回具体错误。
func Run(ctx context.Context, output io.Writer) error {
	configPath, err := config.ExecutablePath()
	if err != nil {
		return err
	}

	agentConfig, created, err := config.LoadOrCreate(configPath)
	if err != nil {
		return err
	}
	if created {
		fmt.Fprintf(output, "已创建配置文件: %s\n", configPath)
	}

	backend := client.NewBackend(backendBaseURL, requestTimeout)
	qrCode, err := backend.RequestQRCode(ctx)
	if err != nil {
		return err
	}
	if err := printQRCode(output, qrCode.URL); err != nil {
		return err
	}

	fmt.Fprintln(output, "请使用微信扫描二维码完成登录，正在等待确认...")
	openID, err := backend.WaitForLogin(
		ctx,
		qrCode.SceneString,
		time.Duration(qrCode.ExpireSeconds)*time.Second,
	)
	if err != nil {
		return err
	}

	networkInfo, err := client.LookupNetwork(ctx, requestTimeout)
	if err != nil {
		return err
	}
	deviceID := agentConfig.DeviceID()
	if deviceID == "" {
		deviceID, err = generateDeviceID()
		if err != nil {
			return err
		}
	}

	agentConfig.Update(openID, deviceID, networkInfo.PublicIPv4)
	if err := config.Write(configPath, agentConfig); err != nil {
		return err
	}
	if err := backend.BindDevice(ctx, client.DeviceBinding{
		DeviceID:   deviceID,
		OpenID:     openID,
		PublicIPv4: networkInfo.PublicIPv4,
		ISP:        networkInfo.ISP,
		Province:   networkInfo.Province,
	}); err != nil {
		return err
	}
	fmt.Fprintln(output, "登录成功，设备信息已保存并完成绑定。")
	fmt.Fprintf(output, "公网 IPv4: %s\n", networkInfo.PublicIPv4)
	fmt.Fprintf(output, "device_id: %s\n", deviceID)
	return nil
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
