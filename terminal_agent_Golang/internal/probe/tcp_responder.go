package probe

import (
	"context"
	"fmt"
	"net"
	"sync"
)

// TCPResponder 通过 TCP handshake 回复在线 Agent 的探测。
type TCPResponder struct {
	listeners []net.Listener
	closeOnce sync.Once
	closeErr  error
}

// StartTCPResponder 启动 TCP 33434 回复监听。
//
// 参数:
//   - ctx: 控制监听退出的 Context。
//   - enableIPv6: 是否同时监听 IPv6。
//
// 返回值: 已启动的回复器；任一监听失败时关闭已有监听并返回错误。
func StartTCPResponder(ctx context.Context, enableIPv6 bool) (*TCPResponder, error) {
	responder := &TCPResponder{}
	networks := []string{"tcp4"}
	if enableIPv6 {
		networks = append(networks, "tcp6")
	}
	for _, network := range networks {
		listener, err := net.Listen(network, fmt.Sprintf(":%d", tcpResponderPort))
		if err != nil {
			_ = responder.Close()
			return nil, fmt.Errorf("监听 %s TCP %d 端口失败: %w", network, tcpResponderPort, err)
		}
		responder.listeners = append(responder.listeners, listener)
		go responder.serve(listener)
	}
	go func() {
		<-ctx.Done()
		_ = responder.Close()
	}()
	return responder, nil
}

// Close 关闭所有 TCP 回复监听。
//
// 参数: 无。
// 返回值: 首个关闭错误；重复调用返回首次结果。
func (responder *TCPResponder) Close() error {
	responder.closeOnce.Do(func() {
		for _, listener := range responder.listeners {
			if err := listener.Close(); err != nil && responder.closeErr == nil {
				responder.closeErr = err
			}
		}
	})
	return responder.closeErr
}

// serve 接受探测连接并及时释放，TCP handshake 本身即为探测回复。
//
// 参数:
//   - listener: 已绑定的 TCP listener。
//
// 返回值: 无；监听关闭或接受失败时退出。
func (responder *TCPResponder) serve(listener net.Listener) {
	for {
		connection, err := listener.Accept()
		if err != nil {
			return
		}
		_ = connection.Close()
	}
}
