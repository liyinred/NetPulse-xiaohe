package probe

import (
	"context"
	"encoding/hex"
	"fmt"
	"net"
	"net/netip"
	"strconv"
	"strings"
	"time"
)

// mtrASNQuery 将公网 IP 转为 Team Cymru DNS 名称。
// 参数: address 为跳点 IP。返回值: 查询名称；非公网地址返回空字符串。
func mtrASNQuery(address netip.Addr) string {
	address = address.Unmap()
	if !address.IsGlobalUnicast() || address.IsPrivate() {
		return ""
	}
	for _, block := range []string{"100.64.0.0/10", "192.0.0.0/24", "192.0.2.0/24", "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "240.0.0.0/4", "2001:db8::/32", "2001::/23", "3fff::/20", "64:ff9b:1::/48", "100::/64"} {
		if netip.MustParsePrefix(block).Contains(address) {
			return ""
		}
	}
	if address.Is4() {
		bytes := address.As4()
		return fmt.Sprintf("%d.%d.%d.%d.origin.asn.cymru.com.", bytes[3], bytes[2], bytes[1], bytes[0])
	}
	bytes := address.As16()
	digits := hex.EncodeToString(bytes[:])
	var query strings.Builder
	for index := len(digits) - 1; index >= 0; index-- {
		query.WriteByte(digits[index])
		query.WriteByte('.')
	}
	return query.String() + "origin6.asn.cymru.com."
}

// lookupMTRASNs 使用标准库查询并校验公网 IP 的 Origin ASN。
// 参数: ctx 控制取消，address 为跳点 IP。返回值: 去重的 ASN；超时或无记录返回空列表。
func lookupMTRASNs(ctx context.Context, address netip.Addr) []uint32 {
	result := make([]uint32, 0)
	query := mtrASNQuery(address)
	if query == "" {
		return result
	}
	lookupCtx, cancel := context.WithTimeout(ctx, 300*time.Millisecond)
	defer cancel()
	records, err := net.DefaultResolver.LookupTXT(lookupCtx, query)
	if err != nil {
		return result
	}
	seen := make(map[uint32]bool)
	for _, record := range records {
		fields := strings.Split(record, "|")
		if len(fields) < 2 {
			continue
		}
		prefix, err := netip.ParsePrefix(strings.TrimSpace(fields[1]))
		if err != nil || !prefix.Contains(address.Unmap()) {
			continue
		}
		for _, value := range strings.Fields(fields[0]) {
			number, err := strconv.ParseUint(value, 10, 32)
			if err == nil && number > 0 && !seen[uint32(number)] {
				seen[uint32(number)] = true
				result = append(result, uint32(number))
			}
		}
	}
	return result
}
