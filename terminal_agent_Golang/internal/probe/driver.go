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
	probeTimeout = 300 * time.Millisecond
	tcpPort      = 80
	udpPort      = 33434
)

type pendingICMP struct {
	target string
	result chan time.Duration
	sentAt time.Time
}

// icmpDriver 使用单个源地址共享 ICMP socket 和接收循环。
type icmpDriver struct {
	connection *icmp.PacketConn
	protocol   int
	echoType   icmp.Type
	replyType  icmp.Type
	identifier int
	mu         sync.Mutex
	sequence   uint16
	pending    map[uint16]pendingICMP
}

// newICMPDriver 创建并启动指定源地址的共享 ICMP Driver。
//
// 参数:
//   - source: 本机公网源地址。
//
// 返回值: 可并发探测目标的 Driver；socket 创建失败时返回错误。
func newICMPDriver(source netip.Addr) (*icmpDriver, error) {
	network := "ip4:icmp"
	protocol := 1
	echoType := icmp.Type(ipv4.ICMPTypeEcho)
	replyType := icmp.Type(ipv4.ICMPTypeEchoReply)
	if source.Is6() {
		network = "ip6:ipv6-icmp"
		protocol = 58
		echoType = ipv6.ICMPTypeEchoRequest
		replyType = ipv6.ICMPTypeEchoReply
	}
	connection, err := icmp.ListenPacket(network, source.String())
	if err != nil {
		return nil, fmt.Errorf("创建 IPv%d ICMP socket 失败: %w", sourceVersion(source), err)
	}
	driver := &icmpDriver{
		connection: connection,
		protocol:   protocol,
		echoType:   echoType,
		replyType:  replyType,
		identifier: os.Getpid() & 0xffff,
		pending:    make(map[uint16]pendingICMP),
	}
	go driver.receive()
	return driver, nil
}

// sourceVersion 返回地址对应的 IP 版本编号。
//
// 参数:
//   - source: IPv4 或 IPv6 地址。
//
// 返回值: IPv4 返回 4，IPv6 返回 6。
func sourceVersion(source netip.Addr) int {
	if source.Is4() {
		return 4
	}
	return 6
}

// Close 关闭共享 ICMP socket。
//
// 参数: 无。
// 返回值: socket 关闭结果。
func (driver *icmpDriver) Close() error {
	return driver.connection.Close()
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
	case rtt := <-pending.result:
		return rtt, nil
	}
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

// probeTCP 使用指定源地址探测目标 TCP 80 端口。
//
// 参数:
//   - ctx: 控制单次连接超时或取消的 Context。
//   - source: 本机公网源地址。
//   - target: 同版本目标公网地址。
//
// 返回值: 连接成功或 connection refused 的 RTT；其他错误表示丢包。
func probeTCP(
	ctx context.Context,
	source netip.Addr,
	target netip.Addr,
) (time.Duration, error) {
	network := "tcp4"
	if source.Is6() {
		network = "tcp6"
	}
	dialer := net.Dialer{
		LocalAddr: &net.TCPAddr{IP: net.IP(source.AsSlice())},
	}
	startedAt := time.Now()
	connection, err := dialer.DialContext(
		ctx,
		network,
		net.JoinHostPort(target.String(), fmt.Sprint(tcpPort)),
	)
	rtt := time.Since(startedAt)
	if err == nil {
		_ = connection.Close()
		return rtt, nil
	}
	if errors.Is(err, syscall.ECONNREFUSED) {
		return rtt, nil
	}
	return 0, err
}

// probeUDP 使用指定源地址发送 UDP datagram 并等待回复或端口不可达。
//
// 参数:
//   - ctx: 控制单次读写超时或取消的 Context。
//   - source: 本机公网源地址。
//   - target: 同版本目标公网地址。
//
// 返回值: 收到 UDP 回复或 connection refused 的 RTT；其他错误表示丢包。
func probeUDP(
	ctx context.Context,
	source netip.Addr,
	target netip.Addr,
) (time.Duration, error) {
	network := "udp4"
	if source.Is6() {
		network = "udp6"
	}
	connection, err := net.DialUDP(
		network,
		&net.UDPAddr{IP: net.IP(source.AsSlice())},
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
	if _, err := connection.Write([]byte("netpulse")); err != nil {
		return 0, err
	}
	buffer := make([]byte, 64)
	if _, err := connection.Read(buffer); err != nil {
		if errors.Is(err, syscall.ECONNREFUSED) {
			return time.Since(startedAt), nil
		}
		return 0, err
	}
	return time.Since(startedAt), nil
}
