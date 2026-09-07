package probe

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/netip"
	"os"
	"sync"
	"syscall"
	"time"

	"golang.org/x/net/icmp"
	"golang.org/x/net/ipv4"
	"golang.org/x/net/ipv6"
)

const (
	probeTimeout     = time.Duration(maximumAverageLatencyMS) * time.Millisecond
	tcpResponderPort = 33434
	tcpPort          = 80
	udpPort          = 33434
)

var errICMPDriverClosed = errors.New("ICMP Driver 已关闭")

type pendingICMP struct {
	target string
	result chan time.Duration
	sentAt time.Time
}

// icmpDriver 使用单个源地址共享 ICMP socket 和接收循环。
type icmpDriver struct {
	connection    *icmp.PacketConn
	protocol      int
	echoType      icmp.Type
	replyType     icmp.Type
	identifier    int
	mu            sync.Mutex
	sequence      uint16
	pending       map[uint16]pendingICMP
	done          chan struct{}
	terminalErr   error
	terminateOnce sync.Once
	closeOnce     sync.Once
	closeErr      error
}

// newICMPDriver 创建并启动指定 IP 版本的共享 ICMP Driver。
//
// 参数:
//   - ipVersion: IP 版本，仅支持 4 或 6。
//
// 返回值: 可并发探测目标的 Driver；版本无效或 socket 创建失败时返回错误。
func newICMPDriver(ipVersion int) (*icmpDriver, error) {
	if ipVersion != 4 && ipVersion != 6 {
		return nil, fmt.Errorf("不支持的 ICMP IP 版本: %d", ipVersion)
	}
	network := "ip4:icmp"
	listenAddress := "0.0.0.0"
	protocol := 1
	echoType := icmp.Type(ipv4.ICMPTypeEcho)
	replyType := icmp.Type(ipv4.ICMPTypeEchoReply)
	if ipVersion == 6 {
		network = "ip6:ipv6-icmp"
		listenAddress = "::"
		protocol = 58
		echoType = ipv6.ICMPTypeEchoRequest
		replyType = ipv6.ICMPTypeEchoReply
	}
	connection, err := icmp.ListenPacket(network, listenAddress)
	if err != nil {
		return nil, fmt.Errorf("创建 IPv%d ICMP socket 失败: %w", ipVersion, err)
	}
	driver := &icmpDriver{
		connection: connection,
		protocol:   protocol,
		echoType:   echoType,
		replyType:  replyType,
		identifier: os.Getpid() & 0xffff,
		pending:    make(map[uint16]pendingICMP),
		done:       make(chan struct{}),
	}
	go driver.receive()
	return driver, nil
}

// Close 关闭共享 ICMP socket。
//
// 参数: 无。
// 返回值: socket 关闭结果。
func (driver *icmpDriver) Close() error {
	driver.closeOnce.Do(func() {
		driver.terminate(errICMPDriverClosed)
		driver.closeErr = driver.connection.Close()
	})
	return driver.closeErr
}

// Probe 向单个同版本目标发送一次 ICMP Echo 并等待匹配响应。
//
// 参数:
//   - ctx: 控制单次探测超时或取消的 Context。
//   - target: 目标公网 IP。
//
// 返回值: 成功响应的 RTT；超时、发送失败或响应无效时返回错误。
func (driver *icmpDriver) Probe(
	ctx context.Context,
	target netip.Addr,
) (time.Duration, error) {
	select {
	case <-driver.done:
		return 0, driver.terminalError()
	default:
	}
	sequence, pending := driver.reserve(target.String())
	defer driver.release(sequence)
	message := icmp.Message{
		Type: driver.echoType,
		Code: 0,
		Body: &icmp.Echo{
			ID:   driver.identifier,
			Seq:  int(sequence),
			Data: []byte("netpulse"),
		},
	}
	payload, err := message.Marshal(nil)
	if err != nil {
		return 0, fmt.Errorf("编码 ICMP 请求失败: %w", err)
	}
	destination := &net.IPAddr{IP: net.IP(target.AsSlice())}
	if _, err := driver.connection.WriteTo(payload, destination); err != nil {
		return 0, fmt.Errorf("发送 ICMP 请求失败: %w", err)
	}
	select {
	case <-ctx.Done():
		return 0, ctx.Err()
	case <-driver.done:
		return 0, driver.terminalError()
	case rtt := <-pending.result:
		return rtt, nil
	}
}

// terminate 记录 ICMP Driver 的终止原因并通知全部等待中的探测。
//
// 参数:
//   - err: receive loop 异常或主动关闭对应的终止原因。
//
// 返回值: 无。
func (driver *icmpDriver) terminate(err error) {
	driver.terminateOnce.Do(func() {
		driver.mu.Lock()
		driver.terminalErr = err
		driver.mu.Unlock()
		close(driver.done)
	})
}

// terminalError 返回 ICMP Driver 已记录的终止原因。
//
// 参数: 无。
// 返回值: Driver 的终止错误；尚未终止时返回 nil。
func (driver *icmpDriver) terminalError() error {
	driver.mu.Lock()
	defer driver.mu.Unlock()
	return driver.terminalErr
}

// reserve 分配当前未使用的 ICMP Sequence 并登记待匹配响应。
//
// 参数:
//   - target: 目标 IP 文本。
//
// 返回值: 分配的 Sequence 和响应 Channel。
func (driver *icmpDriver) reserve(target string) (uint16, pendingICMP) {
	driver.mu.Lock()
	defer driver.mu.Unlock()
	for {
		driver.sequence++
		if _, exists := driver.pending[driver.sequence]; exists {
			continue
		}
		pending := pendingICMP{
			target: target,
			result: make(chan time.Duration, 1),
			sentAt: time.Now(),
		}
		driver.pending[driver.sequence] = pending
		return driver.sequence, pending
	}
}

// release 移除已完成或超时的 ICMP 待响应记录。
//
// 参数:
//   - sequence: 要释放的 ICMP Sequence。
//
// 返回值: 无。
func (driver *icmpDriver) release(sequence uint16) {
	driver.mu.Lock()
	delete(driver.pending, sequence)
	driver.mu.Unlock()
}

// receive 持续读取共享 socket 并将 Echo Reply 投递给对应探测。
//
// 参数: 无。
// 返回值: 无；socket 关闭后退出。
func (driver *icmpDriver) receive() {
	buffer := make([]byte, 1500)
	for {
		readCount, peer, err := driver.connection.ReadFrom(buffer)
		if err != nil {
			driver.terminate(fmt.Errorf("ICMP receive loop 异常退出: %w", err))
			return
		}
		message, err := icmp.ParseMessage(driver.protocol, buffer[:readCount])
		if err != nil {
			continue
		}
		echo, ok := message.Body.(*icmp.Echo)
		if message.Type != driver.replyType || !ok || echo.ID != driver.identifier {
			continue
		}
		driver.deliver(uint16(echo.Seq), peer.String())
	}
}

// deliver 校验响应来源并通知对应 ICMP 探测。
//
// 参数:
//   - sequence: Echo Reply 中的 Sequence。
//   - peer: 响应来源地址文本。
//
// 返回值: 无。
func (driver *icmpDriver) deliver(sequence uint16, peer string) {
	peerHost, _, splitErr := net.SplitHostPort(peer)
	if splitErr == nil {
		peer = peerHost
	}
	if parsed, err := netip.ParseAddr(peer); err == nil {
		peer = parsed.Unmap().String()
	}
	driver.mu.Lock()
	pending, exists := driver.pending[sequence]
	driver.mu.Unlock()
	if !exists || pending.target != peer {
		return
	}
	select {
	case pending.result <- time.Since(pending.sentAt):
	default:
	}
}

// probeTCP 根据在线状态探测 Agent 回复端口或原有 TCP 80 端口。
// tcpResponderEnabled 参数为 true 时要求 Agent 端口连接成功。
//
// 参数:
//   - ctx: 控制单次连接超时或取消的 Context。
//   - target: 同版本目标公网地址。
//
// 返回值: 连接成功的 RTT；传统模式也接受 connection refused，其他错误表示丢包。
func probeTCP(
	ctx context.Context,
	target netip.Addr,
	tcpResponderEnabled bool,
) (time.Duration, error) {
	network := "tcp4"
	if target.Is6() {
		network = "tcp6"
	}
	port := tcpPort
	if tcpResponderEnabled {
		port = tcpResponderPort
	}
	dialer := net.Dialer{}
	startedAt := time.Now()
	connection, err := dialer.DialContext(
		ctx,
		network,
		net.JoinHostPort(target.String(), fmt.Sprint(port)),
	)
	rtt := time.Since(startedAt)
	if err == nil {
		_ = connection.Close()
		return rtt, nil
	}
	if !tcpResponderEnabled && errors.Is(err, syscall.ECONNREFUSED) {
		return rtt, nil
	}
	return 0, err
}

// probeUDP 使用系统路由选择的本地地址发送 UDP datagram 并等待 Agent 回复。
//
// 参数:
//   - ctx: 控制单次读写超时或取消的 Context。
//   - target: 同版本目标公网地址。
//
// 返回值: 收到载荷匹配的 UDP 回复时返回 RTT；其他错误表示丢包。
func probeUDP(
	ctx context.Context,
	target netip.Addr,
) (time.Duration, error) {
	network := "udp4"
	if target.Is6() {
		network = "udp6"
	}
	connection, err := net.DialUDP(
		network,
		nil,
		&net.UDPAddr{IP: net.IP(target.AsSlice()), Port: udpPort},
	)
	if err != nil {
		return 0, err
	}
	defer connection.Close()
	deadline, ok := ctx.Deadline()
	if ok {
		_ = connection.SetDeadline(deadline)
	}
	startedAt := time.Now()
	if _, err := connection.Write([]byte(udpProbePayload)); err != nil {
		return 0, err
	}
	buffer := make([]byte, len(udpProbePayload)+1)
	readCount, err := connection.Read(buffer)
	if err != nil {
		return 0, err
	}
	if string(buffer[:readCount]) != udpProbePayload {
		return 0, errors.New("UDP 探测回复载荷不匹配")
	}
	return time.Since(startedAt), nil
}
