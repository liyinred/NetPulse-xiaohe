// Package probe 实现同版本目标合并和持续网络探测。
package probe

import (
	"fmt"
	"net/netip"
	"sort"

	"netpulse/terminal-agent/internal/client"
)

const (
	modeCrossISP      = "cross_isp"
	modeCrossProvince = "cross_province"
)

var provinceNamesByCode = map[int]string{
	2: "北京", 3: "福建", 4: "甘肃", 5: "广东", 6: "广西", 7: "贵州",
	8: "海南", 9: "河北", 10: "河南", 11: "黑龙江", 12: "湖北", 13: "湖南",
	14: "吉林", 15: "江苏", 16: "江西", 17: "辽宁", 18: "内蒙古", 19: "宁夏",
	20: "青海", 21: "山东", 22: "山西", 23: "陕西", 24: "上海", 25: "四川",
	26: "天津", 27: "西藏", 28: "新疆", 29: "云南", 30: "浙江", 31: "重庆",
	32: "安徽", 33: "香港", 34: "台湾", 35: "澳门",
}

var ispNamesByCode = map[int]string{
	1: "电信",
	2: "移动",
	3: "联通",
	4: "其他",
}

// Target 保存规范化目标地址、网络属性及其所属分类集合。
type Target struct {
	Address  netip.Addr
	ISP      int
	Province int
	Modes    []string
}

// NodeName 返回目标的省份与运营商节点名称。
//
// 参数: 无。
// 返回值: “{省份}{运营商}节点”格式的目标名称；编码未知时使用“未知”或“其他”。
func (target Target) NodeName() string {
	provinceName := provinceNamesByCode[target.Province]
	if provinceName == "" {
		provinceName = "未知"
	}
	ispName := ispNamesByCode[target.ISP]
	if ispName == "" {
		ispName = "其他"
	}
	return provinceName + ispName + "节点"
}

// TargetSnapshot 保存当前双栈源地址及同版本合并目标。
type TargetSnapshot struct {
	IPv4 []Target
	IPv6 []Target
}

// MergeTargets 校验地址族并合并同版本分类目标。
//
// 参数:
//   - response: 中央服务返回的分类目标列表。
//   - sourceIPv4: 当前公网 IPv4。
//   - sourceIPv6: 当前公网 IPv6，未获取到时为空。
//
// 返回值: 按 IP 规范化去重后的双栈目标；响应无效时返回错误。
func MergeTargets(
	response client.ProbeTargets,
	sourceIPv4 netip.Addr,
	sourceIPv6 *netip.Addr,
) (TargetSnapshot, error) {
	if response.SourceIPv4 != sourceIPv4.String() {
		return TargetSnapshot{}, fmt.Errorf("中央服务返回的 source_ipv4 不匹配")
	}
	if response.CrossISPIPv4Targets == nil || response.CrossProvinceIPv4Targets == nil {
		return TargetSnapshot{}, fmt.Errorf("中央服务响应缺少 IPv4 分类目标列表")
	}
	ipv4, err := mergeVersionTargets(
		response.CrossISPIPv4Targets,
		response.CrossProvinceIPv4Targets,
		4,
	)
	if err != nil {
		return TargetSnapshot{}, err
	}
	snapshot := TargetSnapshot{IPv4: ipv4}
	if sourceIPv6 == nil {
		if response.SourceIPv6 != nil ||
			response.CrossISPIPv6Targets != nil ||
			response.CrossProvinceIPv6Targets != nil {
			return TargetSnapshot{}, fmt.Errorf("无 IPv6 源地址时服务端返回了 IPv6 目标")
		}
		return snapshot, nil
	}
	if response.SourceIPv6 == nil || *response.SourceIPv6 != sourceIPv6.String() {
		return TargetSnapshot{}, fmt.Errorf("中央服务返回的 source_ipv6 不匹配")
	}
	if response.CrossISPIPv6Targets == nil || response.CrossProvinceIPv6Targets == nil {
		return TargetSnapshot{}, fmt.Errorf("中央服务响应缺少 IPv6 分类目标列表")
	}
	ipv6, err := mergeVersionTargets(
		response.CrossISPIPv6Targets,
		response.CrossProvinceIPv6Targets,
		6,
	)
	if err != nil {
		return TargetSnapshot{}, err
	}
	snapshot.IPv6 = ipv6
	return snapshot, nil
}

// mergeVersionTargets 将同版本的两个分类列表合并并保留分类集合。
//
// 参数:
//   - crossISP: 异网目标列表。
//   - crossProvince: 跨省目标列表。
//   - version: 期望的 IP 版本。
//
// 返回值: 按地址排序的唯一目标；目标地址无效或版本错误时返回错误。
func mergeVersionTargets(
	crossISP []client.ProbeTarget,
	crossProvince []client.ProbeTarget,
	version int,
) ([]Target, error) {
	targetModes := make(map[netip.Addr]map[string]struct{})
	targetMetadata := make(map[netip.Addr]client.ProbeTarget)
	lists := []struct {
		mode    string
		targets []client.ProbeTarget
	}{
		{mode: modeCrossISP, targets: crossISP},
		{mode: modeCrossProvince, targets: crossProvince},
	}
	for _, list := range lists {
		for _, item := range list.targets {
			address, err := netip.ParseAddr(item.PublicIP)
			if err != nil || version == 4 && !address.Is4() ||
				version == 6 && !address.Is6() {
				return nil, fmt.Errorf("%s 列表包含无效 IPv%d 地址: %s", list.mode, version, item.PublicIP)
			}
			address = address.Unmap()
			if targetModes[address] == nil {
				targetModes[address] = make(map[string]struct{})
				targetMetadata[address] = item
			}
			targetModes[address][list.mode] = struct{}{}
		}
	}
	addresses := make([]netip.Addr, 0, len(targetModes))
	for address := range targetModes {
		addresses = append(addresses, address)
	}
	sort.Slice(addresses, func(left, right int) bool {
		return addresses[left].Less(addresses[right])
	})
	targets := make([]Target, 0, len(addresses))
	for _, address := range addresses {
		modes := make([]string, 0, 2)
		if _, ok := targetModes[address][modeCrossISP]; ok {
			modes = append(modes, modeCrossISP)
		}
		if _, ok := targetModes[address][modeCrossProvince]; ok {
			modes = append(modes, modeCrossProvince)
		}
		metadata := targetMetadata[address]
		targets = append(targets, Target{
			Address:  address,
			ISP:      metadata.ISP,
			Province: metadata.Province,
			Modes:    modes,
		})
	}
	return targets, nil
}
