package probe

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/netip"
	"os"
	"time"

	"golang.org/x/net/icmp"
	"golang.org/x/net/ipv4"
	"golang.org/x/net/ipv6"
	"netpulse/terminal-agent/internal/client"
)

const mtrPollRetryDelay = time.Second

// MTRRunner 长轮询、执行并上报双向 MTR 方向任务。
type MTRRunner struct {
	backend    *client.Backend
	deviceID   string
	sourceIPv4 netip.Addr
	sourceIPv6 *netip.Addr
	output     io.Writer
}

// NewMTRRunner 创建双向 MTR 任务 Runner。
//
// 参数:
//   - backend: FastAPI 中央服务 Client。
//   - deviceID: Agent 设备标识。
//   - sourceIPv4: 当前公网 IPv4。
//   - sourceIPv6: 当前公网 IPv6，未获取到时为空。
//   - output: 接收运行状态的 Writer。
//
// 返回值: 已配置但尚未开始轮询的 Runner。
func NewMTRRunner(backend *client.Backend, deviceID string, sourceIPv4 netip.Addr, sourceIPv6 *netip.Addr, output io.Writer) *MTRRunner {
	return &MTRRunner{backend, deviceID, sourceIPv4, sourceIPv6, output}
}

// Run 持续轮询并串行执行当前设备的 MTR 任务。
//
// 参数:
//   - ctx: 控制轮询和执行退出的 Context。
//
// 返回值: Context 取消时返回其错误。
func (runner *MTRRunner) Run(ctx context.Context) error {
	for {
		task, err := runner.backend.PollMTRTask(ctx, runner.deviceID)
		if err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			fmt.Fprintf(runner.output, "轮询双向 MTR 任务失败: %v\n", err)
			if waitErr := waitUntil(ctx, time.Now().Add(mtrPollRetryDelay)); waitErr != nil {
				return waitErr
			}
			continue
		}
		if task != nil {
			runner.execute(ctx, *task)
		}
	}
}

// recoverTaskPanic 捕获单个 MTR 任务的异常，避免终止整个 Agent。
//
// 参数:
//   - taskID: 当前执行的 MTR 主任务标识。
//
// 返回值: 无；捕获到异常时输出任务日志。
func (runner *MTRRunner) recoverTaskPanic(taskID int64) {
	if recovered := recover(); recovered != nil {
		fmt.Fprintf(runner.output, "双向 MTR 任务 %d 执行异常: %v\n", taskID, recovered)
	}
}

// execute 校验地址快照、执行 ICMP MTR 并上报方向结果。
//
// 参数:
//   - ctx: 控制执行和上报取消的 Context。
//   - task: 中央服务已租约分配的方向任务。
//
// 返回值: 无；可上报的执行失败通过 error_code 结束任务，任务无效或异常时输出日志。
func (runner *MTRRunner) execute(ctx context.Context, task client.MTRTask) {
	defer runner.recoverTaskPanic(task.MTRTaskID)

	source, err := netip.ParseAddr(task.SourceIP)
	if err != nil {
		fmt.Fprintf(runner.output, "双向 MTR 任务 %d 无效: source_ip 无效\n", task.MTRTaskID)
		return
	}
	target, err := netip.ParseAddr(task.TargetIP)
	if err != nil || source.BitLen() != target.BitLen() ||
		task.IPVersion == 4 && (!source.Is4() || !target.Is4()) ||
		task.IPVersion == 6 && (!source.Is6() || !target.Is6()) ||
		(task.IPVersion != 4 && task.IPVersion != 6) {
		fmt.Fprintf(runner.output, "双向 MTR 任务 %d 无效: 源目标 IP 版本不匹配\n", task.MTRTaskID)
		return
	}
	if task.IPVersion == 4 && source != runner.sourceIPv4 ||
		task.IPVersion == 6 && (runner.sourceIPv6 == nil || source != *runner.sourceIPv6) {
		fmt.Fprintf(runner.output, "双向 MTR 任务 %d 无效: 当前源 IP 已变化或不可用\n", task.MTRTaskID)
		return
	}
	started := time.Now()
	hops, traceErr := traceICMPMTR(ctx, target)
	var errorCode *string
	if traceErr != nil {
		value := "MTR_EXECUTION_FAILED"
		errorCode = &value
	}
	request := client.MTRResultRequest{MTRTaskID: task.MTRTaskID, Direction: task.Direction, LeaseToken: task.LeaseToken, DeviceID: runner.deviceID, SourceIP: source.String(), TargetIP: target.String(), StartedAt: started.Unix(), FinishedAt: time.Now().Unix(), Hops: hops, ErrorCode: errorCode}
	if err := runner.backend.SubmitMTRResult(ctx, request); err != nil {
		fmt.Fprintf(runner.output, "双向 MTR 任务 %d 上报失败: %v\n", task.MTRTaskID, err)
	}
}

// traceICMPMTR 使用原生 ICMP Echo 和递增 TTL 生成逐跳路径统计。
//
// 参数:
//   - ctx: 控制探测取消的 Context。
//   - target: 中央服务下发且已校验地址族的目标 IP。
//
// 返回值: 至多 32 跳、每跳三次的 ICMP 统计；初始化失败时返回错误。
func traceICMPMTR(ctx context.Context, target netip.Addr) ([]client.MTRHop, error) {
	if !target.Is4() && !target.Is6() {
		return nil, fmt.Errorf("MTR 目标 IP 地址族无效")
	}
	ipVersion := 4
	network, protocol := "ip4:icmp", 1
	echoType, echoReply, timeExceeded := icmp.Type(ipv4.ICMPTypeEcho), icmp.Type(ipv4.ICMPTypeEchoReply), icmp.Type(ipv4.ICMPTypeTimeExceeded)
	if target.Is6() {
		ipVersion = 6
		network, protocol = "ip6:ipv6-icmp", 58
		echoType, echoReply, timeExceeded = icmp.Type(ipv6.ICMPTypeEchoRequest), icmp.Type(ipv6.ICMPTypeEchoReply), icmp.Type(ipv6.ICMPTypeTimeExceeded)
	}
	connection, err := icmp.ListenPacket(network, "")
	if err != nil {
		return nil, fmt.Errorf("创建 MTR ICMP socket 失败: %w", err)
	}
	defer connection.Close()
	packet4, packet6 := connection.IPv4PacketConn(), connection.IPv6PacketConn()
	if (ipVersion == 4 && packet4 == nil) || (ipVersion == 6 && packet6 == nil) {
		return nil, fmt.Errorf("MTR ICMP socket 未提供 IPv%d 控制连接", ipVersion)
	}
	identifier := os.Getpid() & 0xffff
	sequence := 0
	hops := make([]client.MTRHop, 0, 32)
	for ttl := 1; ttl <= 32; ttl++ {
		var received int
		var total time.Duration
		var address *string
		reached := false
		for attempt := 0; attempt < 3; attempt++ {
			if ctx.Err() != nil {
				return hops, ctx.Err()
			}
			if ipVersion == 4 {
				if err := packet4.SetTTL(ttl); err != nil {
					return hops, err
				}
			} else if err := packet6.SetHopLimit(ttl); err != nil {
				return hops, err
			}
			sequence++
			message := icmp.Message{Type: echoType, Body: &icmp.Echo{ID: identifier, Seq: sequence, Data: []byte("netpulse-mtr")}}
			payload, marshalErr := message.Marshal(nil)
			if marshalErr != nil {
				return hops, marshalErr
			}
			started := time.Now()
			if _, writeErr := connection.WriteTo(payload, &net.IPAddr{IP: net.IP(target.AsSlice())}); writeErr != nil {
				continue
			}
			_ = connection.SetReadDeadline(time.Now().Add(probeTimeout))
			buffer := make([]byte, 1500)
			for {
				count, peer, readErr := connection.ReadFrom(buffer)
				if readErr != nil {
					break
				}
				response, parseErr := icmp.ParseMessage(protocol, buffer[:count])
				if parseErr != nil || (response.Type != echoReply && response.Type != timeExceeded) {
					continue
				}
				peerIP, _, splitErr := net.SplitHostPort(peer.String())
				if splitErr == nil {
					peer = &net.IPAddr{IP: net.ParseIP(peerIP)}
				}
				value := peer.String()
				if parsed, parseErr := netip.ParseAddr(value); parseErr == nil {
					value = parsed.Unmap().String()
				}
				address = &value
				received++
				total += time.Since(started)
				reached = response.Type == echoReply
				break
			}
		}
		var average *int
		if received > 0 {
			value := int(total.Milliseconds() / int64(received))
			average = &value
		}
		hops = append(hops, client.MTRHop{TTL: ttl, Address: address, Sent: 3, Received: received, LossRate: (3 - received) * 1000 / 3, AverageLatencyMS: average})
		if reached {
			break
		}
	}
	return hops, nil
}
