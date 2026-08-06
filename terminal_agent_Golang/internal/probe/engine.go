package probe

import (
	"context"
	"crypto/rand"
	"fmt"
	"io"
	"math"
	"math/big"
	"net/netip"
	"strings"
	"sync"
	"time"

	"netpulse/terminal-agent/internal/client"
)

const (
	probeCount         = 100
	windowLength       = time.Minute
	reportJitterWindow = 10 * time.Second
)

var protocolNames = []string{"icmp", "tcp", "udp"}

// Engine 编排目标刷新、自然分钟探测和结果/告警上报。
type Engine struct {
	backend    *client.Backend
	deviceID   string
	sourceIPv4 netip.Addr
	sourceIPv6 *netip.Addr
	output     io.Writer
}

type protocolStats struct {
	attempted int
	succeeded int
	rttTotal  time.Duration
}

type targetStats struct {
	target Target
	icmp   protocolStats
	tcp    protocolStats
	udp    protocolStats
}

type sourceWindow struct {
	version int
	source  netip.Addr
	targets []Target
	driver  *icmpDriver
}

// NewEngine 创建持续探测 Engine。
//
// 参数:
//   - backend: FastAPI 中央服务 Client。
//   - deviceID: Agent 设备标识。
//   - sourceIPv4: 当前公网 IPv4。
//   - sourceIPv6: 当前公网 IPv6，未获取到时为空。
//   - output: 接收运行状态的 Writer。
//
// 返回值: 已配置但尚未启动的 Engine。
func NewEngine(
	backend *client.Backend,
	deviceID string,
	sourceIPv4 netip.Addr,
	sourceIPv6 *netip.Addr,
	output io.Writer,
) *Engine {
	return &Engine{
		backend:    backend,
		deviceID:   deviceID,
		sourceIPv4: sourceIPv4,
		sourceIPv6: sourceIPv6,
		output:     output,
	}
}

// Run 按自然分钟持续刷新目标、执行探测并上报结果。
//
// 参数:
//   - ctx: 控制 Engine 退出的 Context。
//
// 返回值: 初始化、目标刷新或探测失败时返回错误；取消时返回 Context 错误。
func (engine *Engine) Run(ctx context.Context) error {
	snapshot, err := engine.fetchTargets(ctx)
	if err != nil {
		return err
	}
	if len(snapshot.IPv4) == 0 && len(snapshot.IPv6) == 0 {
		return fmt.Errorf("当前获取的异网和跨省探测目标为空")
	}
	drivers, err := engine.openICMPDrivers()
	if err != nil {
		return err
	}
	defer func() {
		for _, driver := range drivers {
			_ = driver.Close()
		}
	}()
	nextWindow := time.Now().Truncate(windowLength).Add(windowLength)
	fmt.Fprintf(engine.output, "持续探测将在 %s 开始。\n", nextWindow.Format("15:04:05"))
	if err := waitUntil(ctx, nextWindow); err != nil {
		return err
	}

	for {
		windowStart := nextWindow
		windowEnd := windowStart.Add(windowLength)
		refreshChannel := make(chan TargetSnapshot, 1)
		refreshError := make(chan error, 1)
		go func() {
			refreshed, refreshErr := engine.fetchTargets(ctx)
			if refreshErr != nil {
				refreshError <- refreshErr
				return
			}
			refreshChannel <- refreshed
		}()

		results, err := engine.runWindow(
			ctx,
			windowStart,
			windowEnd,
			snapshot,
			drivers,
		)
		if err != nil {
			return err
		}
		engine.printWindowResults(windowStart, windowEnd, results)
		engine.submitWindowResults(ctx, windowEnd.Unix(), results)
		engine.submitWindowAlerts(ctx, windowEnd.Unix(), results)
		select {
		case refreshed := <-refreshChannel:
			if len(refreshed.IPv4) == 0 && len(refreshed.IPv6) == 0 {
				fmt.Fprintln(engine.output, "当前获取的异网和跨省探测目标为空，下一窗口沿用当前目标。")
			} else {
				snapshot = refreshed
			}
		case refreshErr := <-refreshError:
			fmt.Fprintf(engine.output, "刷新探测目标失败，下一窗口沿用当前目标: %v\n", refreshErr)
		default:
			fmt.Fprintln(engine.output, "刷新探测目标尚未完成，下一窗口沿用当前目标。")
		}
		nextWindow = windowEnd
	}
}

// openICMPDrivers 为每个可用 IP 版本创建共享 ICMP Driver。
//
// 参数: 无。
// 返回值: 按 IP 版本索引的 Driver；任一 socket 初始化失败时返回错误。
func (engine *Engine) openICMPDrivers() (map[int]*icmpDriver, error) {
	drivers := make(map[int]*icmpDriver)
	ipv4Driver, err := newICMPDriver(4)
	if err != nil {
		return nil, err
	}
	drivers[4] = ipv4Driver
	if engine.sourceIPv6 != nil {
		ipv6Driver, err := newICMPDriver(6)
		if err != nil {
			_ = ipv4Driver.Close()
			return nil, err
		}
		drivers[6] = ipv6Driver
	}
	return drivers, nil
}

// fetchTargets 查询并合并中央服务返回的双栈分类目标。
//
// 参数:
//   - ctx: 控制 HTTP 请求取消的 Context。
//
// 返回值: 规范化目标快照；请求或响应无效时返回错误。
func (engine *Engine) fetchTargets(ctx context.Context) (TargetSnapshot, error) {
	response, err := engine.backend.FetchProbeTargets(
		ctx,
		engine.deviceID,
		engine.sourceIPv4,
		engine.sourceIPv6,
	)
	if err != nil {
		return TargetSnapshot{}, err
	}
	return MergeTargets(response, engine.sourceIPv4, engine.sourceIPv6)
}

// runWindow 并发执行一个自然分钟内的全部双栈逻辑目标。
//
// 参数:
//   - ctx: 控制 Engine 退出的 Context。
//   - windowStart: 自然分钟窗口起点。
//   - windowEnd: 自然分钟窗口终点。
//   - snapshot: 本窗口使用的目标快照。
//   - drivers: 按 IP 版本索引的共享 ICMP Driver。
//
// 返回值: 各源地址的目标统计；窗口被取消时返回错误。
func (engine *Engine) runWindow(
	ctx context.Context,
	windowStart time.Time,
	windowEnd time.Time,
	snapshot TargetSnapshot,
	drivers map[int]*icmpDriver,
) ([]sourceWindowResult, error) {
	windowContext, cancel := context.WithDeadline(ctx, windowEnd)
	defer cancel()
	windows := []sourceWindow{
		{version: 4, source: engine.sourceIPv4, targets: snapshot.IPv4, driver: drivers[4]},
	}
	if engine.sourceIPv6 != nil {
		windows = append(windows, sourceWindow{
			version: 6,
			source:  *engine.sourceIPv6,
			targets: snapshot.IPv6,
			driver:  drivers[6],
		})
	}
	results := make([]sourceWindowResult, len(windows))
	var waitGroup sync.WaitGroup
	for index, source := range windows {
		index, source := index, source
		waitGroup.Add(1)
		go func() {
			defer waitGroup.Done()
			results[index] = engine.runSourceWindow(windowContext, windowStart, source)
		}()
	}
	waitGroup.Wait()
	if err := waitUntil(ctx, windowEnd); err != nil {
		return nil, err
	}
	if ctx.Err() != nil {
		return nil, ctx.Err()
	}
	if err := validateWindowResults(results); err != nil {
		return nil, err
	}
	return results, nil
}

type sourceWindowResult struct {
	version int
	source  netip.Addr
	stats   []targetStats
}

// printWindowResults 在终端输出一个完整自然分钟的三协议探测结果。
//
// 参数:
//   - windowStart: 自然分钟窗口起点。
//   - windowEnd: 自然分钟窗口终点。
//   - results: 当前窗口按源地址汇总的目标统计。
//
// 返回值: 无。
func (engine *Engine) printWindowResults(
	windowStart time.Time,
	windowEnd time.Time,
	results []sourceWindowResult,
) {
	fmt.Fprintf(
		engine.output,
		"\n%s 至 %s 整分钟探测结果:\n",
		windowStart.Format("2006-01-02 15:04:05"),
		windowEnd.Format("15:04:05"),
	)
	for _, result := range results {
		for _, stats := range result.stats {
			modeNames := make([]string, 0, len(stats.target.Modes))
			for _, mode := range stats.target.Modes {
				if mode == modeCrossISP {
					modeNames = append(modeNames, "异网")
				} else {
					modeNames = append(modeNames, "跨省")
				}
			}
			fmt.Fprintf(
				engine.output,
				"IPv%d %s -> %s [%s]\n",
				result.version,
				result.source,
				stats.target.NodeName(),
				strings.Join(modeNames, "/"),
			)
			protocols := []struct {
				name  string
				stats protocolStats
			}{
				{name: "ICMP", stats: stats.icmp},
				{name: "TCP", stats: stats.tcp},
				{name: "UDP", stats: stats.udp},
			}
			for _, protocol := range protocols {
				summary := summarize(protocol.stats)
				fmt.Fprintf(
					engine.output,
					"  %s: 成功 %d/%d，丢包率 %.1f%%，平均延迟 %d ms\n",
					protocol.name,
					protocol.stats.succeeded,
					protocol.stats.attempted,
					float64(summary.LossRate)/10,
					summary.AverageLatencyMS,
				)
			}
		}
	}
}

// validateWindowResults 校验非空逻辑目标均完成固定探测次数。
//
// 参数:
//   - results: 当前自然分钟的双栈目标统计。
//
// 返回值: 全部协议均完成 100 次时返回 nil，否则返回错误。
func validateWindowResults(results []sourceWindowResult) error {
	for _, result := range results {
		for _, stats := range result.stats {
			attempts := []int{
				stats.icmp.attempted,
				stats.tcp.attempted,
				stats.udp.attempted,
			}
			for index, attempted := range attempts {
				if attempted != probeCount {
					return fmt.Errorf(
						"IPv%d 目标 %s 的 %s 探测仅完成 %d/%d 次",
						result.version,
						stats.target.Address,
						protocolNames[index],
						attempted,
						probeCount,
					)
				}
			}
		}
	}
	return nil
}

// runSourceWindow 并发执行一个源地址下的全部协议逻辑目标。
//
// 参数:
//   - ctx: 截止时间与窗口结束对齐的 Context。
//   - windowStart: 自然分钟窗口起点。
//   - source: 当前 IP 版本的源地址、目标和 ICMP Driver。
//
// 返回值: 当前源地址下所有目标的三协议统计。
func (engine *Engine) runSourceWindow(
	ctx context.Context,
	windowStart time.Time,
	source sourceWindow,
) sourceWindowResult {
	stats := make([]targetStats, len(source.targets))
	var waitGroup sync.WaitGroup
	for targetIndex, target := range source.targets {
		stats[targetIndex].target = target
		for _, protocol := range protocolNames {
			targetIndex, target, protocol := targetIndex, target, protocol
			waitGroup.Add(1)
			go func() {
				defer waitGroup.Done()
				result := engine.runLogicalTarget(
					ctx,
					windowStart,
					source,
					target,
					protocol,
				)
				switch protocol {
				case "icmp":
					stats[targetIndex].icmp = result
				case "tcp":
					stats[targetIndex].tcp = result
				case "udp":
					stats[targetIndex].udp = result
				}
			}()
		}
	}
	waitGroup.Wait()
	return sourceWindowResult{version: source.version, source: source.source, stats: stats}
}

// runLogicalTarget 按绝对计划时刻执行 100 次单协议探测。
//
// 参数:
//   - ctx: 截止时间与窗口结束对齐的 Context。
//   - windowStart: 自然分钟窗口起点。
//   - source: 当前源地址和 ICMP Driver。
//   - target: 唯一目标及所属分类。
//   - protocol: icmp、tcp 或 udp。
//
// 返回值: 本逻辑目标的尝试次数、成功次数和 RTT 总和。
func (engine *Engine) runLogicalTarget(
	ctx context.Context,
	windowStart time.Time,
	source sourceWindow,
	target Target,
	protocol string,
) protocolStats {
	interval := windowLength / probeCount
	stats := protocolStats{}
	for sequence := 0; sequence < probeCount; sequence++ {
		plannedAt := windowStart.Add(time.Duration(sequence) * interval)
		if err := waitUntil(ctx, plannedAt); err != nil {
			break
		}
		attemptContext, cancel := context.WithTimeout(ctx, probeTimeout)
		rtt, err := probeOnce(
			attemptContext,
			source.driver,
			target.Address,
			protocol,
		)
		cancel()
		stats.attempted++
		if err == nil {
			stats.succeeded++
			stats.rttTotal += rtt
			continue
		}
	}
	return stats
}

// probeOnce 调用对应协议 Driver 执行一次探测。
//
// 参数:
//   - ctx: 控制 300ms 超时或取消的 Context。
//   - icmpDriver: 当前 IP 版本的共享 ICMP Driver。
//   - target: 同版本目标地址。
//   - protocol: icmp、tcp 或 udp。
//
// 返回值: 成功响应 RTT；丢包或协议无效时返回错误。
func probeOnce(
	ctx context.Context,
	icmpDriver *icmpDriver,
	target netip.Addr,
	protocol string,
) (time.Duration, error) {
	switch protocol {
	case "icmp":
		return icmpDriver.Probe(ctx, target)
	case "tcp":
		return probeTCP(ctx, target)
	case "udp":
		return probeUDP(ctx, target)
	default:
		return 0, fmt.Errorf("不支持的探测协议: %s", protocol)
	}
}

// buildWindowAlerts 按目标、协议和分类生成自然分钟聚合告警。
//
// 参数:
//   - deviceID: Agent 设备标识。
//   - windowEnd: 自然分钟窗口结束 Unix 时间戳。
//   - results: 当前自然分钟的探测统计。
//
// 返回值: 每个发生丢包的聚合维度对应一条告警。
func buildWindowAlerts(
	deviceID string,
	windowEnd int64,
	results []sourceWindowResult,
) []client.ProbeAlertRequest {
	alerts := make([]client.ProbeAlertRequest, 0)
	for _, result := range results {
		for _, targetStats := range result.stats {
			protocols := []struct {
				name  string
				stats protocolStats
			}{
				{name: "icmp", stats: targetStats.icmp},
				{name: "tcp", stats: targetStats.tcp},
				{name: "udp", stats: targetStats.udp},
			}
			for _, protocol := range protocols {
				if protocol.stats.attempted == protocol.stats.succeeded {
					continue
				}
				lossRate := summarize(protocol.stats).LossRate
				for _, mode := range targetStats.target.Modes {
					alerts = append(alerts, client.ProbeAlertRequest{
						EventID:       generateEventID(),
						DeviceID:      deviceID,
						ProbeMode:     mode,
						IPVersion:     result.version,
						SourceIP:      result.source.String(),
						TargetIP:      targetStats.target.Address.String(),
						ProtocolType:  protocol.name,
						LossRate:      lossRate,
						UnixTimestamp: windowEnd,
					})
				}
			}
		}
	}
	return alerts
}

// submitWindowAlerts 异步上报一个自然分钟内的聚合丢包告警。
//
// 参数:
//   - ctx: 控制随机延迟等待和 HTTP 请求取消的 Context。
//   - windowEnd: 自然分钟窗口结束 Unix 时间戳。
//   - results: 当前自然分钟的探测统计。
//
// 返回值: 无；没有丢包时不发起请求。
func (engine *Engine) submitWindowAlerts(
	ctx context.Context,
	windowEnd int64,
	results []sourceWindowResult,
) {
	alerts := buildWindowAlerts(engine.deviceID, windowEnd, results)
	if len(alerts) == 0 {
		return
	}
	request := client.ProbeAlertsRequest{Alerts: alerts}
	engine.submitWithJitter(
		ctx,
		windowEnd,
		"分钟聚合告警上报失败",
		func(submitContext context.Context) error {
			return engine.backend.SubmitProbeAlerts(submitContext, request)
		},
	)
}

// submitWindowResults 将统计按目标分类投影并异步上报。
//
// 参数:
//   - ctx: 控制随机延迟等待和 HTTP 请求取消的 Context。
//   - windowEnd: 自然分钟窗口结束 Unix 时间戳。
//   - results: 各源地址的目标统计。
//
// 返回值: 无。
func (engine *Engine) submitWindowResults(
	ctx context.Context,
	windowEnd int64,
	results []sourceWindowResult,
) {
	for _, result := range results {
		for _, mode := range []string{modeCrossISP, modeCrossProvince} {
			targets := make([]client.TargetResult, 0)
			for _, stats := range result.stats {
				if !containsMode(stats.target.Modes, mode) {
					continue
				}
				targets = append(targets, client.TargetResult{
					TargetIP: stats.target.Address.String(),
					ICMP:     summarize(stats.icmp),
					TCP:      summarize(stats.tcp),
					UDP:      summarize(stats.udp),
				})
			}
			if len(targets) == 0 {
				continue
			}
			request := client.ProbeResultRequest{
				DeviceID:      engine.deviceID,
				ProbeMode:     mode,
				IPVersion:     result.version,
				SourceIP:      result.source.String(),
				UnixTimestamp: windowEnd,
				Targets:       targets,
			}
			engine.submitWithJitter(
				ctx,
				windowEnd,
				"分钟探测结果上报失败",
				func(submitContext context.Context) error {
					return engine.backend.SubmitProbeResult(submitContext, request)
				},
			)
		}
	}
}

// submitWithJitter 在窗口结束后的随机十秒内异步执行一次上报。
//
// 参数:
//   - ctx: 控制延迟等待和 HTTP 请求取消的 Context。
//   - windowEnd: 自然分钟窗口结束 Unix 时间戳。
//   - failureMessage: 上报失败时输出的提示文本。
//   - submit: 执行具体上报请求的函数。
//
// 返回值: 无。
func (engine *Engine) submitWithJitter(
	ctx context.Context,
	windowEnd int64,
	failureMessage string,
	submit func(context.Context) error,
) {
	plannedAt := time.Unix(windowEnd, 0).Add(randomReportDelay())
	go func() {
		if err := waitUntil(ctx, plannedAt); err != nil {
			return
		}
		if err := submit(ctx); err != nil {
			fmt.Fprintf(engine.output, "%s: %v\n", failureMessage, err)
		}
	}()
}

// randomReportDelay 生成小于十秒的加密安全随机上报延迟。
//
// 参数: 无。
// 返回值: [0, 10s) 范围内的随机时长；随机源失败时返回零。
func randomReportDelay() time.Duration {
	upperBound := big.NewInt(int64(reportJitterWindow))
	randomValue, err := rand.Int(rand.Reader, upperBound)
	if err != nil {
		return 0
	}
	return time.Duration(randomValue.Int64())
}

// summarize 将内部统计转换为服务端整数千分比和整数毫秒结果。
//
// 参数:
//   - stats: 单个逻辑目标的内部统计。
//
// 返回值: 符合中央服务契约的协议汇总结果。
func summarize(stats protocolStats) client.ProtocolResult {
	if stats.attempted == 0 || stats.succeeded == 0 {
		return client.ProtocolResult{LossRate: 1000, AverageLatencyMS: 1000}
	}
	lost := stats.attempted - stats.succeeded
	lossRate := int(math.Round(float64(lost) / float64(stats.attempted) * 1000))
	averageMilliseconds := int(math.Round(
		float64(stats.rttTotal) / float64(stats.succeeded) / float64(time.Millisecond),
	))
	return client.ProtocolResult{
		LossRate:         lossRate,
		AverageLatencyMS: averageMilliseconds,
	}
}

// containsMode 判断分类集合是否包含指定分类。
//
// 参数:
//   - modes: 目标所属分类集合。
//   - expected: 要查找的分类。
//
// 返回值: 分类存在时返回 True。
func containsMode(modes []string, expected string) bool {
	for _, mode := range modes {
		if mode == expected {
			return true
		}
	}
	return false
}

// waitUntil 等待绝对计划时刻或 Context 取消。
//
// 参数:
//   - ctx: 控制等待取消的 Context。
//   - plannedAt: 计划执行的绝对时刻。
//
// 返回值: 到达计划时刻返回 nil，取消时返回 Context 错误。
func waitUntil(ctx context.Context, plannedAt time.Time) error {
	delay := time.Until(plannedAt)
	if delay <= 0 {
		return nil
	}
	timer := time.NewTimer(delay)
	defer timer.Stop()
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}

// generateEventID 使用加密安全随机数生成 UUID v4 告警标识。
//
// 参数: 无。
// 返回值: 36 字符 UUID；随机源失败时返回零值格式 UUID。
func generateEventID() string {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		return "00000000-0000-4000-8000-000000000000"
	}
	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80
	return fmt.Sprintf(
		"%x-%x-%x-%x-%x",
		value[0:4], value[4:6], value[6:8], value[8:10], value[10:16],
	)
}
