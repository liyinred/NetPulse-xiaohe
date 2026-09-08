package client

import (
	"context"
	"errors"
	"fmt"
	"net"
	"net/http/httptrace"
	"net/netip"
)

// ErrNATDevice 表示设备的实际连接源地址无法通过公网直连检查。
var ErrNATDevice = errors.New("不允许 NAT 设备使用，请在公网 IP 直接配置于本机的设备上运行")

// traceLocalAddress 记录本次 HTTP 连接实际使用的本地源 IP。
// 参数: ctx 为请求 Context。返回值: 带追踪的 Context 和接收源 IP 的指针。
func traceLocalAddress(ctx context.Context) (context.Context, *netip.Addr) {
	localAddress := new(netip.Addr)
	trace := &httptrace.ClientTrace{
		// GotConn 从实际连接读取源地址，兼容连接池复用和多网卡路由。
		GotConn: func(info httptrace.GotConnInfo) {
			if address, ok := info.Conn.LocalAddr().(*net.TCPAddr); ok {
				*localAddress = address.AddrPort().Addr().Unmap()
			}
		},
	}
	return httptrace.WithClientTrace(ctx, trace), localAddress
}

// validateDirectPublicIP 比较外部观察地址与实际连接源地址，拒绝 NAT 和无法确认的连接。
// 参数: publicAddress 为外部观察 IP，localAddress 为 TCP 本地源 IP。返回值: 直连时为空，否则为错误。
func validateDirectPublicIP(publicAddress, localAddress netip.Addr) error {
	publicAddress = publicAddress.Unmap()
	localAddress = localAddress.Unmap()
	if !publicAddress.IsGlobalUnicast() || publicAddress.IsPrivate() || netip.MustParsePrefix("100.64.0.0/10").Contains(publicAddress) {
		return fmt.Errorf("%w：外部返回的地址 %s 不是有效公网地址", ErrNATDevice, publicAddress)
	}
	if !localAddress.IsValid() {
		return fmt.Errorf("%w：无法确认本地连接源 IP", ErrNATDevice)
	}
	if localAddress != publicAddress {
		return fmt.Errorf("%w：本地连接源 IP 为 %s，外部观察 IP 为 %s", ErrNATDevice, localAddress, publicAddress)
	}
	return nil
}
