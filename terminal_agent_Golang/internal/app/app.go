// Package app 编排 Agent 的设备身份、二维码登录和绑定流程。
package app

import (
	"bufio"
	"context"
	"crypto/rand"
	"fmt"
	"io"
	"net/netip"
	"strings"
	"time"

	"netpulse/terminal-agent/internal/client"
	"netpulse/terminal-agent/internal/config"
	"netpulse/terminal-agent/internal/probe"

	qrcode "github.com/skip2/go-qrcode"
)

const (
	backendBaseURL  = "http://175.4.50.59:8086"
	requestTimeout  = 10 * time.Second
	ipv4RetryDelay  = 3 * time.Second
	ipv4MaxAttempts = 3
)

// Run 每次通过二维码更新设备绑定，并按用户确认启动持续探测。
//
// 参数:
//   - ctx: 控制 Agent 退出的 Context。
//   - input: 接收持续探测确认输入的 Reader。
//   - output: 输出二维码和运行状态的 Writer。
//
// 返回值: 流程成功时返回 nil，否则返回具体错误。
func Run(ctx context.Context, input io.Reader, output io.Writer) error {
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

	deviceID := agentConfig.DeviceID()
	if deviceID == "" {
		deviceID, err = generateDeviceID()
		if err != nil {
			return err
		}
		agentConfig.SetDeviceID(deviceID)
	}
	if err := config.Write(configPath, agentConfig); err != nil {
		return err
	}

	backend := client.NewBackend(backendBaseURL, requestTimeout)
	sourceIPv4, err := waitForPublicIPv4(ctx, output, backend)
	if err != nil {
		return err
	}

	var sourceIPv6 *netip.Addr
	publicIPv6, ipv6Err := backend.GetPublicIPv6(ctx)
	if ipv6Err == nil {
		sourceIPv6 = &publicIPv6
	}

	qrCode, err := backend.RequestQRCode(ctx)
	if err != nil {
		return err
	}
	if err := printQRCode(output, qrCode.URL); err != nil {
		return err
	}

	fmt.Fprintln(output, "请使用微信扫描二维码完成设备绑定更新，正在等待确认...")
	bindingInfo, err := backend.WaitForLogin(
		ctx,
		qrCode.SceneString,
		deviceID,
		sourceIPv4,
		sourceIPv6,
		time.Duration(qrCode.ExpireSeconds)*time.Second,
	)
	if err != nil {
		return fmt.Errorf("设备绑定更新失败: %w", err)
	}

	fmt.Fprintln(output, "登录成功，中央服务已完成设备绑定更新。")
	printBindingInfo(output, bindingInfo)

	confirmed, err := confirmContinuousProbe(input, output)
	if err != nil {
		return err
	}
	if !confirmed {
		fmt.Fprintln(output, "已取消持续探测。")
		return nil
	}
	fmt.Fprintln(output, "正在获取异网和跨省探测目标...")
	probeEngine := probe.NewEngine(
		backend,
		deviceID,
		sourceIPv4,
		sourceIPv6,
		output,
	)
	return probeEngine.Run(ctx)
}

// confirmContinuousProbe 显示 Y/N 提示并监听用户输入。
//
// 参数:
//   - input: 接收终端输入的 Reader。
//   - output: 输出提示和格式错误信息的 Writer。
//
// 返回值: 输入 Y 时返回 True，输入 N 时返回 False；读取失败时返回错误。
func confirmContinuousProbe(input io.Reader, output io.Writer) (bool, error) {
	reader := bufio.NewReader(input)
	for {
		if _, err := fmt.Fprint(output, "是否进行持续探测(Y/N): "); err != nil {
			return false, fmt.Errorf("输出持续探测提示失败: %w", err)
		}
		answer, err := reader.ReadString('\n')
		answer = strings.TrimSpace(answer)
		if strings.EqualFold(answer, "Y") {
			return true, nil
		}
		if strings.EqualFold(answer, "N") {
			return false, nil
		}
		if err != nil {
			return false, fmt.Errorf("读取持续探测确认失败: %w", err)
		}
		fmt.Fprintln(output, "请输入 Y 或 N。")
	}
}

// printBindingInfo 在终端展示绑定成功后的设备和网络信息。
//
// 参数:
//   - output: 接收设备信息的 Writer。
//   - bindingInfo: 中央服务返回的设备网络信息。
//
// 返回值: 无。
func printBindingInfo(output io.Writer, bindingInfo client.BindingInfo) {
	fmt.Fprintf(output, "设备 ID: %s\n", bindingInfo.DeviceID)
	fmt.Fprintf(output, "公网 IPv4: %s\n", bindingInfo.PublicIPv4)
	if bindingInfo.PublicIPv6 != nil {
		fmt.Fprintf(output, "公网 IPv6: %s\n", *bindingInfo.PublicIPv6)
	}
	fmt.Fprintf(
		output,
		"省市: %s %s\n",
		bindingInfo.ProvinceName,
		bindingInfo.City,
	)
	fmt.Fprintf(output, "运营商: %s\n", bindingInfo.ISPName)
}

// waitForPublicIPv4 最多尝试三次获取公网 IPv4。
//
// 参数:
//   - ctx: 控制重试取消的 Context。
//   - output: 输出失败提示和重试状态的 Writer。
//   - backend: FastAPI 中央服务 Client。
//
// 返回值: 获取成功的公网 IPv4；取消或三次尝试均失败时返回错误。
func waitForPublicIPv4(
	ctx context.Context,
	output io.Writer,
	backend *client.Backend,
) (netip.Addr, error) {
	for attempt := 1; ; attempt++ {
		publicIPv4, err := backend.GetPublicIPv4(ctx)
		if err == nil {
			return publicIPv4, nil
		}
		if attempt >= ipv4MaxAttempts {
			return netip.Addr{}, fmt.Errorf(
				"公网 IPv4 获取失败，已尝试 %d 次: %w",
				ipv4MaxAttempts,
				err,
			)
		}
		fmt.Fprintf(
			output,
			"第 %d/%d 次公网 IPv4 获取失败，将在 %s 后重试: %v\n",
			attempt,
			ipv4MaxAttempts,
			ipv4RetryDelay,
			err,
		)

		retryTimer := time.NewTimer(ipv4RetryDelay)
		select {
		case <-ctx.Done():
			if !retryTimer.Stop() {
				<-retryTimer.C
			}
			return netip.Addr{}, ctx.Err()
		case <-retryTimer.C:
		}
	}
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
