package probe

import (
	"context"
	"fmt"
	"io"
	"net/netip"
	"sync"
	"time"

	"netpulse/terminal-agent/internal/client"
)

const onDemandRetryDelay = time.Second

// OnDemandRunner 长轮询、执行并上报临时 IP 按需探测任务。
type OnDemandRunner struct {
	backend    *client.Backend
	deviceID   string
	sourceIPv4 netip.Addr
	sourceIPv6 *netip.Addr
	output     io.Writer
}

// NewOnDemandRunner 创建按需探测任务 Runner。
//
// 参数:
//   - backend: FastAPI 中央服务 Client。
//   - deviceID: Agent 设备标识。
//   - sourceIPv4: 当前公网 IPv4。
//   - sourceIPv6: 当前公网 IPv6，未获取到时为空。
//   - output: 接收运行状态的 Writer。
//
// 返回值: 已配置但尚未开始轮询的 Runner。
func NewOnDemandRunner(
	backend *client.Backend,
	deviceID string,
	sourceIPv4 netip.Addr,
	sourceIPv6 *netip.Addr,
	output io.Writer,
) *OnDemandRunner {
	return &OnDemandRunner{
		backend: backend, deviceID: deviceID, sourceIPv4: sourceIPv4,
		sourceIPv6: sourceIPv6, output: output,
	}
}

// Run 持续长轮询任务并为每个任务启动独立 goroutine。
//
// 参数:
//   - ctx: 控制轮询和全部节点任务退出的 Context。
//
// 返回值: Context 取消时返回其错误。
func (runner *OnDemandRunner) Run(ctx context.Context) error {
	for {
		task, err := runner.backend.PollOnDemandTask(ctx, runner.deviceID)
		if err != nil {
			if ctx.Err() != nil {
				return ctx.Err()
			}
			fmt.Fprintf(runner.output, "轮询临时 IP 探测任务失败: %v\n", err)
			if err := waitUntil(ctx, time.Now().Add(onDemandRetryDelay)); err != nil {
				return err
			}
			continue
		}
		if task != nil {
			go runner.executeTask(ctx, *task)
		}
	}
}

// executeTask 校验、执行并一次性上报一个节点任务。
//
// 参数:
//   - ctx: 控制 Agent 全局退出的 Context。
//   - task: 中央服务已原子分配的节点任务。
//
// 返回值: 无；失败原因输出到终端。
func (runner *OnDemandRunner) executeTask(ctx context.Context, task client.OnDemandTask) {
	source, target, err := runner.validateTask(task)
	if err != nil {
		fmt.Fprintf(runner.output, "临时 IP 探测任务 %d 无效: %v\n", task.ID, err)
		return
	}
	driver, err := newICMPDriver(task.IPVersion)
	if err != nil {
		fmt.Fprintf(runner.output, "临时 IP 探测任务 %d 初始化失败: %v\n", task.ID, err)
		return
	}
	defer driver.Close()

	startedAt := time.Now()
	results := make(map[string]client.ProtocolResult, len(protocolNames))
	var mutex sync.Mutex
	var waitGroup sync.WaitGroup
	for _, protocol := range protocolNames {
		protocol := protocol
		waitGroup.Add(1)
		go func() {
			defer waitGroup.Done()
			stats := runOnDemandProtocol(
				ctx, startedAt, driver, target, protocol,
				task.ProbeCount, time.Duration(task.IntervalMS)*time.Millisecond,
				time.Duration(task.TimeoutMS)*time.Millisecond,
			)
			mutex.Lock()
			results[protocol] = summarize(stats)
			mutex.Unlock()
		}()
	}
	waitGroup.Wait()
	request := client.OnDemandResultRequest{
		TaskID: task.ID, DeviceID: runner.deviceID,
		SourceIP: source.String(), TargetIP: target.String(),
		StartedAt: startedAt.Unix(), FinishedAt: time.Now().Unix(),
		Results: client.OnDemandResults{
			ICMP: results["icmp"], TCP: results["tcp"], UDP: results["udp"],
		},
	}
	if err := runner.backend.SubmitOnDemandResult(ctx, request); err != nil {
		fmt.Fprintf(runner.output, "临时 IP 探测任务 %d 上报失败: %v\n", task.ID, err)
		return
	}
	fmt.Fprintf(runner.output, "临时 IP 探测任务 %d 已完成: %s\n", task.ID, target)
}

// validateTask 校验固定探测参数、地址族及当前源地址。
//
// 参数:
//   - task: 中央服务下发的节点任务。
//
// 返回值: 当前源地址和目标地址；字段无效时返回错误。
func (runner *OnDemandRunner) validateTask(
	task client.OnDemandTask,
) (netip.Addr, netip.Addr, error) {
	if task.ProbeCount != 10 || task.IntervalMS != 100 || task.TimeoutMS != 300 {
		return netip.Addr{}, netip.Addr{}, fmt.Errorf("探测参数不是 10 次/100ms/300ms")
	}
	source, err := netip.ParseAddr(task.SourceIP)
	if err != nil {
		return netip.Addr{}, netip.Addr{}, fmt.Errorf("source_ip 无效")
	}
	target, err := netip.ParseAddr(task.TargetIP)
	if err != nil || source.BitLen() != target.BitLen() ||
		task.IPVersion == 4 && !source.Is4() || task.IPVersion == 6 && !source.Is6() {
		return netip.Addr{}, netip.Addr{}, fmt.Errorf("源目标 IP 版本不匹配")
	}
	if task.IPVersion == 4 && source != runner.sourceIPv4 {
		return netip.Addr{}, netip.Addr{}, fmt.Errorf("IPv4 源地址已变化")
	}
	if task.IPVersion == 6 && (runner.sourceIPv6 == nil || source != *runner.sourceIPv6) {
		return netip.Addr{}, netip.Addr{}, fmt.Errorf("IPv6 源地址不可用或已变化")
	}
	return source, target, nil
}

// runOnDemandProtocol 按绝对时刻对一个协议执行固定次数探测。
//
// 参数:
//   - ctx: 控制任务取消的 Context。
//   - startedAt: 一秒发送窗口起点。
//   - driver: 当前地址族的 ICMP Driver。
//   - target: 临时目标 IP。
//   - protocol: icmp、tcp 或 udp。
//   - count: 固定探测次数。
//   - interval: 固定发送间隔。
//   - timeout: 单次探测超时。
//
// 返回值: 当前协议的尝试次数、成功次数和 RTT 总和。
func runOnDemandProtocol(
	ctx context.Context,
	startedAt time.Time,
	driver *icmpDriver,
	target netip.Addr,
	protocol string,
	count int,
	interval time.Duration,
	timeout time.Duration,
) protocolStats {
	stats := protocolStats{}
	var mutex sync.Mutex
	var waitGroup sync.WaitGroup
	for sequence := 0; sequence < count; sequence++ {
		if err := waitUntil(ctx, startedAt.Add(time.Duration(sequence)*interval)); err != nil {
			break
		}
		waitGroup.Add(1)
		go func() {
			defer waitGroup.Done()
			attemptContext, cancel := context.WithTimeout(ctx, timeout)
			defer cancel()
			rtt, err := probeOnce(attemptContext, driver, target, protocol)
			mutex.Lock()
			defer mutex.Unlock()
			stats.attempted++
			if err == nil {
				stats.succeeded++
				stats.rttTotal += rtt
			}
		}()
	}
	waitGroup.Wait()
	return stats
}
