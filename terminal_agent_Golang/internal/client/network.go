package client

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const (
	publicIPEndpoint = "https://api.ip.sb/ip"
	ipLookupEndpoint = "https://ip9.com.cn/get"
	maxIPAddressSize = 64
)

var provinceCodes = map[string]int{
	"北京": 2, "福建": 3, "甘肃": 4, "广东": 5, "广西": 6,
	"贵州": 7, "海南": 8, "河北": 9, "河南": 10, "黑龙江": 11,
	"湖北": 12, "湖南": 13, "吉林": 14, "江苏": 15, "江西": 16,
	"辽宁": 17, "内蒙古": 18, "宁夏": 19, "青海": 20, "山东": 21,
	"山西": 22, "陕西": 23, "上海": 24, "四川": 25, "天津": 26,
	"西藏": 27, "新疆": 28, "云南": 29, "浙江": 30, "重庆": 31,
	"安徽": 32, "香港": 33, "台湾": 34, "澳门": 35,
}

// NetworkInfo 保存公网 IPv4 及归一化后的网络属性。
type NetworkInfo struct {
	PublicIPv4 string
	ISP        int
	Province   int
}

type ipLookupResponse struct {
	Ret  int          `json:"ret"`
	Data ipLookupData `json:"data"`
}

type ipLookupData struct {
	IP       string `json:"ip"`
	ISP      string `json:"isp"`
	Province string `json:"prov"`
}

// LookupNetwork 查询当前公网 IPv4 及其归一化运营商和省份编码。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - timeout: 单次 HTTP 请求超时时间。
//
// 返回值: 网络信息；任一查询或响应无效时返回错误。
func LookupNetwork(ctx context.Context, timeout time.Duration) (NetworkInfo, error) {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.DialContext = dialIPv4
	defer transport.CloseIdleConnections()
	httpClient := &http.Client{Timeout: timeout, Transport: transport}

	publicIPv4, err := requestPublicIPv4(ctx, httpClient)
	if err != nil {
		return NetworkInfo{}, err
	}
	ipInfo, err := requestIPInfo(ctx, httpClient, publicIPv4)
	if err != nil {
		return NetworkInfo{}, err
	}
	ipInfo.PublicIPv4 = publicIPv4
	return ipInfo, nil
}

// dialIPv4 强制使用 TCP over IPv4 建立网络连接。
//
// 参数:
//   - ctx: 控制连接取消和超时的 Context。
//   - network: HTTP Transport 提供的网络类型，本函数固定使用 tcp4。
//   - address: 要连接的主机和端口。
//
// 返回值: 建立的网络连接；连接失败时返回错误。
func dialIPv4(ctx context.Context, network string, address string) (net.Conn, error) {
	dialer := &net.Dialer{}
	return dialer.DialContext(ctx, "tcp4", address)
}

// requestPublicIPv4 从公网查询并校验当前设备的 IPv4 地址。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - httpClient: 用于访问公网服务的 HTTP Client。
//
// 返回值: 规范化的公网 IPv4 地址；请求或响应无效时返回错误。
func requestPublicIPv4(ctx context.Context, httpClient *http.Client) (string, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, publicIPEndpoint, nil)
	if err != nil {
		return "", fmt.Errorf("创建公网 IPv4 请求失败: %w", err)
	}

	response, err := httpClient.Do(request)
	if err != nil {
		return "", fmt.Errorf("获取公网 IPv4 失败: %w", err)
	}
	defer response.Body.Close()

	body, err := io.ReadAll(io.LimitReader(response.Body, maxIPAddressSize+1))
	if err != nil {
		return "", fmt.Errorf("读取公网 IPv4 响应失败: %w", err)
	}
	if response.StatusCode < http.StatusOK || response.StatusCode >= http.StatusMultipleChoices {
		return "", fmt.Errorf(
			"公网 IPv4 服务返回 HTTP %d: %s",
			response.StatusCode,
			strings.TrimSpace(string(body)),
		)
	}
	if len(body) > maxIPAddressSize {
		return "", errors.New("公网 IPv4 响应过大")
	}

	ipAddress := net.ParseIP(strings.TrimSpace(string(body)))
	if ipAddress == nil || ipAddress.To4() == nil {
		return "", errors.New("公网 IPv4 服务未返回有效的 IPv4 地址")
	}
	return ipAddress.To4().String(), nil
}

// requestIPInfo 查询公网 IPv4 的运营商和省份，并返回归一化编码。
//
// 参数:
//   - ctx: 控制请求取消的 Context。
//   - httpClient: 用于访问 IP9 接口的 HTTP Client。
//   - ipAddress: 要查询的规范化公网 IPv4 地址。
//
// 返回值: 归一化后的网络属性；请求或响应无效时返回错误。
func requestIPInfo(
	ctx context.Context,
	httpClient *http.Client,
	ipAddress string,
) (NetworkInfo, error) {
	endpoint, err := url.Parse(ipLookupEndpoint)
	if err != nil {
		return NetworkInfo{}, fmt.Errorf("创建 IP 归属信息请求失败: %w", err)
	}
	query := endpoint.Query()
	query.Set("ip", ipAddress)
	endpoint.RawQuery = query.Encode()

	request, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint.String(), nil)
	if err != nil {
		return NetworkInfo{}, fmt.Errorf("创建 IP 归属信息请求失败: %w", err)
	}

	var response ipLookupResponse
	if err := executeJSONRequest(httpClient, request, &response); err != nil {
		return NetworkInfo{}, fmt.Errorf("查询 IP 归属信息失败: %w", err)
	}
	if response.Ret != http.StatusOK {
		return NetworkInfo{}, fmt.Errorf("IP 归属信息接口返回业务状态码 %d", response.Ret)
	}
	responseIP := net.ParseIP(strings.TrimSpace(response.Data.IP))
	if responseIP == nil || responseIP.To4() == nil || responseIP.To4().String() != ipAddress {
		return NetworkInfo{}, errors.New("IP 归属信息响应与查询地址不一致")
	}

	return NetworkInfo{
		ISP:      normalizeISP(response.Data.ISP),
		Province: normalizeProvince(response.Data.Province),
	}, nil
}

// normalizeISP 将运营商名称归一化为设备绑定编码。
//
// 参数:
//   - isp: IP9 返回的运营商名称。
//
// 返回值: 电信为 1、移动为 2、联通为 3，其他为 4。
func normalizeISP(isp string) int {
	switch {
	case strings.Contains(isp, "电信"):
		return 1
	case strings.Contains(isp, "移动"):
		return 2
	case strings.Contains(isp, "联通"):
		return 3
	default:
		return 4
	}
}

// normalizeProvince 将省份名称归一化为设备绑定编码。
//
// 参数:
//   - province: IP9 返回的省份名称或简称。
//
// 返回值: 已知省份对应 2 至 35，空值或未知省份返回 1。
func normalizeProvince(province string) int {
	normalized := strings.TrimPrefix(strings.TrimSpace(province), "中国")
	for _, suffix := range []string{
		"壮族自治区", "回族自治区", "维吾尔自治区", "特别行政区", "自治区", "省", "市",
	} {
		normalized = strings.TrimSuffix(normalized, suffix)
	}
	if code, found := provinceCodes[normalized]; found {
		return code
	}
	return 1
}
