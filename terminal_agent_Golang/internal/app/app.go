// Package app 编排 Agent 的设备身份、二维码登录和绑定流程。
package app

import (
	"bufio"
	"context"
	"crypto/rand"
	"fmt"
	"io"
	"net/netip"
	"os"
	"path/filepath"
	"strings"
	"time"

	"netpulse/terminal-agent/internal/client"
	"netpulse/terminal-agent/internal/config"
	"netpulse/terminal-agent/internal/probe"

	qrcode "github.com/skip2/go-qrcode"
)

const (
	backendBaseURL  = "http://175.4.50.59:8086"
	requestTimeout  = 3 * time.Second
	ipv4RetryDelay  = 3 * time.Second
	ipv4MaxAttempts = 3
	logFileName     = "netpulse-agent.log"
)

// Run 初始化 Linux 防火墙和接口日志，每次通过二维码更新设备绑定，并按用户确认启动持续探测。
//
// 参数:
//   - ctx: 控制 Agent 退出的 Context。
//   - input: 接收持续探测确认输入的 Reader。
//   - output: 输出二维码和运行状态的 Writer。
//
// 返回值: 流程成功时返回 nil，否则返回具体错误。
func Run(ctx context.Context, input io.Reader, output io.Writer) error {
	fmt.Fprintln(output, "NetPulse Agent 正在初始化...")
	configPath, err := config.ExecutablePath()
	if err != nil {
		return err
	}
	logFile, err := openLogFile(configPath)
	if err != nil {
		return err
	}
	defer logFile.Close()
	firewallBackend, err := configureLinuxFirewall(ctx)
	if err != nil {
		fmt.Fprintf(output, "  防火墙：自动配置失败，不影响 Agent 继续运行：%v\n", err)
	}
	if firewallBackend != "" && err == nil {
		fmt.Fprintf(
			output,
			"  防火墙：已通过 Linux %s 放行 UDP 33434 和 TCP 80、33434 的入站及出站流量\n",
			firewallBackend,
		)
	}

	agentConfig, _, err := config.LoadOrCreate(configPath)
	if err != nil {
		return err
	}

	backend := client.NewBackend(backendBaseURL, requestTimeout, logFile)
	deviceID := agentConfig.DeviceID()
	needsNewDeviceID := deviceID == ""
	if !needsNewDeviceID {
		exists, validationErr := backend.DeviceExists(ctx, deviceID)
		if validationErr != nil {
			return fmt.Errorf("验证本地 device_id 失败: %w", validationErr)
		}
		needsNewDeviceID = !exists
	}
	if needsNewDeviceID {
		deviceID, err = generateDeviceID()
		if err != nil {
			return err
		}
		agentConfig.SetDeviceID(deviceID)
	}
	if err := config.Write(configPath, agentConfig); err != nil {
		return err
	}

	sourceIPv4, err := waitForPublicIPv4(ctx, output, backend)
	if err != nil {
		return err
	}
	fmt.Fprintf(output, "  公网 IPv4：%s\n", sourceIPv4)

	var sourceIPv6 *netip.Addr
	publicIPv6, ipv6Err := backend.GetPublicIPv6(ctx)
	if ipv6Err == nil {
		sourceIPv6 = &publicIPv6
		fmt.Fprintf(output, "  公网 IPv6：%s\n", publicIPv6)
	} else {
		fmt.Fprintln(output, "  公网 IPv6：未检测到，本次将仅使用 IPv4")
	}

	qrCode, err := backend.RequestQRCode(ctx)
	if err != nil {
		return err
	}
	fmt.Fprintln(output, "\n初始化完成，请使用微信扫描下方二维码并关注服务号：")
	if err := printQRCode(output, qrCode.URL); err != nil {
		return err
	}

	fmt.Fprintln(output, "正在等待扫码确认...")
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

	printBindingInfo(output, bindingInfo)
	udpResponder, err := probe.StartUDPResponder(ctx, sourceIPv6 != nil)
	if err != nil {
		return err
	}
	defer udpResponder.Close()
	tcpResponder, err := probe.StartTCPResponder(ctx, sourceIPv6 != nil)
	if err != nil {
		return err
	}
	defer tcpResponder.Close()
	onDemandRunner := probe.NewOnDemandRunner(
		backend,
		deviceID,
		sourceIPv4,
		sourceIPv6,
		output,
	)
	mtrRunner := probe.NewMTRRunner(backend, deviceID, sourceIPv4, sourceIPv6, output)
	go func() {
		if runnerErr := mtrRunner.Run(ctx); runnerErr != nil && ctx.Err() == nil {
			fmt.Fprintf(output, "双向 MTR 轮询已停止: %v\n", runnerErr)
		}
	}()

	confirmed, err := confirmContinuousProbe(input, output)
	if err != nil {
		return err
	}
	if !confirmed {
		fmt.Fprintln(output, "已选择按需任务模式。Agent 将保持在线，等待临时 IP 探测与双向 MTR 任务。")
		return onDemandRunner.Run(ctx)
	}
	go func() {
		if runnerErr := onDemandRunner.Run(ctx); runnerErr != nil && ctx.Err() == nil {
			fmt.Fprintf(output, "临时 IP 探测轮询已停止: %v\n", runnerErr)
		}
	}()
	fmt.Fprintln(output, "已选择完整探测模式，正在获取异网和跨省探测目标...")
	probeEngine := probe.NewEngine(
		backend,
		deviceID,
		sourceIPv4,
		sourceIPv6,
		output,
	)
	return probeEngine.Run(ctx)
}

// openLogFile 在配置文件同目录打开默认追加日志文件。
//
// 参数:
//   - configPath: Agent 配置文件的绝对路径。
//
// 返回值: 可追加写入的日志文件；创建或打开失败时返回错误。
func openLogFile(configPath string) (*os.File, error) {
	logPath := filepath.Join(filepath.Dir(configPath), logFileName)
	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return nil, fmt.Errorf("创建日志文件失败: %w", err)
	}
	return logFile, nil
}

// confirmContinuousProbe 显示数字选项并监听用户输入。
//
// 参数:
//   - input: 接收终端输入的 Reader。
//   - output: 输出提示和格式错误信息的 Writer。
//
// 返回值: 输入 1 时返回 True，输入 0 时返回 False；读取失败时返回错误。
func confirmContinuousProbe(input io.Reader, output io.Writer) (bool, error) {
	reader := bufio.NewReader(input)
	for {
		if _, err := fmt.Fprint(
			output,
			"\n请选择 Agent 运行模式：\n"+
				"  0. 按需任务模式：执行临时 IP 探测与双向 MTR\n"+
				"  1. 完整探测模式：在按需任务基础上，持续执行异网与跨省探测\n"+
				"请输入选项（0 或 1）： ",
		); err != nil {
			return false, fmt.Errorf("输出持续探测提示失败: %w", err)
		}
		answer, err := reader.ReadString('\n')
		answer = strings.TrimSpace(answer)
		if answer == "1" {
			return true, nil
		}
		if answer == "0" {
			return false, nil
		}
		if err != nil {
			return false, fmt.Errorf("读取持续探测确认失败: %w", err)
		}
		fmt.Fprintln(output, "输入无效，请输入 0 或 1。")
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
	fmt.Fprintln(output, "\n设备绑定成功，已完成设备信息更新：")
	fmt.Fprintf(output, "  设备 ID：%s\n", bindingInfo.DeviceID)
	fmt.Fprintf(output, "  公网 IPv4：%s\n", bindingInfo.PublicIPv4)
	if bindingInfo.PublicIPv6 != nil {
		fmt.Fprintf(output, "  公网 IPv6：%s\n", *bindingInfo.PublicIPv6)
	} else {
		fmt.Fprintln(output, "  公网 IPv6：未检测到")
	}
	fmt.Fprintf(
		output,
		"  省市：%s %s\n",
		bindingInfo.ProvinceName,
		bindingInfo.City,
	)
	fmt.Fprintf(output, "  运营商：%s\n", bindingInfo.ISPName)
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
				"公网 IPv4 检测失败，已尝试 %d 次：%w",
				ipv4MaxAttempts,
				err,
			)
		}
		fmt.Fprintf(
			output,
			"  公网 IPv4：第 %d/%d 次检测失败，将在 %s 后重试：%v\n",
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
