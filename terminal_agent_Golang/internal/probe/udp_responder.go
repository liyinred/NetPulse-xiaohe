package probe

import (
	"context"
	"fmt"
	"net"
	"sync"
)

const udpProbePayload = "netpulse"

// UDPResponder 在 UDP 33434 端口接收并回复合法探测报文。
type UDPResponder struct {
	connections []*net.UDPConn
	closeOnce   sync.Once
	closeErr    error
}

// StartUDPResponder 启动当前可用地址族的 UDP 探测回复监听。
//
// 参数:
//   - ctx: 控制全部监听退出的 Context。
//   - enableIPv6: 是否同时监听 IPv6 地址。
//
// 返回值: 已启动的回复器；任一端口监听失败时返回错误。
func StartUDPResponder(ctx context.Context, enableIPv6 bool) (*UDPResponder, error) {
	responder := &UDPResponder{}
	type listenAddress struct {
		network string
		address *net.UDPAddr
	}
	addresses := []listenAddress{
		{network: "udp4", address: &net.UDPAddr{IP: net.IPv4zero, Port: udpPort}},
	}
	if enableIPv6 {
		addresses = append(addresses, listenAddress{
			network: "udp6",
			address: &net.UDPAddr{IP: net.IPv6zero, Port: udpPort},
		})
	}
	for _, item := range addresses {
		connection, err := net.ListenUDP(item.network, item.address)
		if err != nil {
			_ = responder.Close()
			return nil, fmt.Errorf("监听 %s UDP %d 端口失败: %w", item.network, udpPort, err)
		}
		responder.connections = append(responder.connections, connection)
		go responder.serve(connection)
	}
	go func() {
		<-ctx.Done()
		_ = responder.Close()
	}()
	return responder, nil
}

// Close 关闭全部 UDP 探测回复监听。
//
// 参数: 无。
// 返回值: 首个 socket 关闭错误；重复调用返回首次结果。
func (responder *UDPResponder) Close() error {
	responder.closeOnce.Do(func() {
		for _, connection := range responder.connections {
			if err := connection.Close(); err != nil && responder.closeErr == nil {
				responder.closeErr = err
			}
		}
	})
	return responder.closeErr
}

// serve 持续接收合法探测报文并向来源地址回复相同载荷。
//
// 参数:
//   - connection: 已绑定地址族和端口的 UDP socket。
//
// 返回值: 无；socket 关闭或读取失败时退出。
func (responder *UDPResponder) serve(connection *net.UDPConn) {
	buffer := make([]byte, len(udpProbePayload)+1)
	for {
		readCount, peer, err := connection.ReadFromUDP(buffer)
		if err != nil {
			return
		}
		if string(buffer[:readCount]) != udpProbePayload {
			continue
		}
		_, _ = connection.WriteToUDP([]byte(udpProbePayload), peer)
	}
}
