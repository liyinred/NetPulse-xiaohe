package app

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"runtime"
	"strings"
)

type firewallPort struct {
	protocol string
	port     string
}

type nftablesRuleset struct {
	Objects []struct {
		Chain *struct {
			Family string `json:"family"`
			Table  string `json:"table"`
			Name   string `json:"name"`
			Hook   string `json:"hook"`
		} `json:"chain,omitempty"`
	} `json:"nftables"`
}

var firewallPorts = []firewallPort{
	{protocol: "udp", port: "33434"},
	{protocol: "tcp", port: "80"},
}

// configureLinuxFirewall 在 Linux 上选择可用防火墙并放行探测端口。
//
// 参数:
//   - ctx: 控制防火墙命令执行的 Context。
//
// 返回值: 配置成功时返回防火墙名称；非 Linux 返回空字符串；配置失败时返回错误。
func configureLinuxFirewall(ctx context.Context) (string, error) {
	if runtime.GOOS != "linux" {
		return "", nil
	}
	if commandExists("firewall-cmd") {
		if _, err := runFirewallCommand(ctx, "firewall-cmd", "--state"); err == nil {
			return "firewalld", configureFirewalld(ctx)
		}
	}
	if commandExists("ufw") {
		status, err := runFirewallCommand(ctx, "ufw", "status")
		if err == nil && strings.Contains(strings.ToLower(status), "status: active") {
			return "UFW", configureUFW(ctx)
		}
	}
	if commandExists("nft") {
		configured, err := configureNftables(ctx)
		if err != nil {
			return "", err
		}
		if configured {
			return "nftables", nil
		}
	}
	if commandExists("iptables") {
		return "iptables", configureIPTables(ctx)
	}
	return "", fmt.Errorf("未检测到可配置的 firewalld、UFW、nftables 或 iptables")
}

// configureFirewalld 为默认 Zone 添加入站端口，并显式允许 IPv4/IPv6 出站流量。
//
// 参数:
//   - ctx: 控制 firewall-cmd 执行的 Context。
//
// 返回值: 全部运行时规则配置成功时返回 nil，否则返回错误。
func configureFirewalld(ctx context.Context) error {
	zoneOutput, err := runFirewallCommand(ctx, "firewall-cmd", "--get-active-zones")
	if err != nil {
		return fmt.Errorf("读取 firewalld 活动 Zone 失败: %w", err)
	}
	zoneFields := strings.Fields(zoneOutput)
	if len(zoneFields) == 0 {
		return fmt.Errorf("firewalld 未发现活动 Zone")
	}
	zoneArgument := "--zone=" + zoneFields[0]
	for _, rule := range firewallPorts {
		if err := runIdempotentFirewalld(
			ctx,
			zoneArgument,
			"--add-port="+rule.port+"/"+rule.protocol,
		); err != nil {
			return err
		}
		for _, family := range []string{"ipv4", "ipv6"} {
			if err := runIdempotentFirewalld(
				ctx,
				"--direct", "--add-rule", family, "filter", "OUTPUT", "0",
				"-p", rule.protocol, "--dport", rule.port, "-j", "ACCEPT",
			); err != nil {
				return err
			}
		}
	}
	return nil
}

// runIdempotentFirewalld 执行允许规则已存在的 firewall-cmd 命令。
//
// 参数:
//   - ctx: 控制命令执行的 Context。
//   - arguments: 传递给 firewall-cmd 的参数。
//
// 返回值: 命令成功或规则已存在时返回 nil，否则返回错误。
func runIdempotentFirewalld(ctx context.Context, arguments ...string) error {
	output, err := runFirewallCommand(ctx, "firewall-cmd", arguments...)
	if err != nil && !strings.Contains(output, "ALREADY_ENABLED") {
		return err
	}
	return nil
}

// configureUFW 通过 UFW 允许探测端口入站和出站。
//
// 参数:
//   - ctx: 控制 ufw 命令执行的 Context。
//
// 返回值: 全部规则配置成功时返回 nil，否则返回错误。
func configureUFW(ctx context.Context) error {
	for _, direction := range []string{"in", "out"} {
		for _, rule := range firewallPorts {
			if _, err := runFirewallCommand(
				ctx,
				"ufw",
				"allow", direction, "proto", rule.protocol,
				"to", "any", "port", rule.port,
			); err != nil {
				return err
			}
		}
	}
	return nil
}

// configureNftables 向原生 nftables 的 INPUT 和 OUTPUT base chain 添加幂等规则。
//
// 参数:
//   - ctx: 控制 nft 命令执行的 Context。
//
// 返回值: 找到 base chain 时返回 True；未找到时返回 False；配置失败时返回错误。
func configureNftables(ctx context.Context) (bool, error) {
	output, err := runFirewallCommand(ctx, "nft", "-j", "list", "ruleset")
	if err != nil {
		return false, nil
	}
	var ruleset nftablesRuleset
	if err := json.Unmarshal([]byte(output), &ruleset); err != nil {
		return false, fmt.Errorf("解析 nftables ruleset 失败: %w", err)
	}
	configured := false
	for _, object := range ruleset.Objects {
		chain := object.Chain
		if chain == nil || chain.Hook != "input" && chain.Hook != "output" {
			continue
		}
		if chain.Family != "inet" && chain.Family != "ip" && chain.Family != "ip6" {
			continue
		}
		chainOutput, err := runFirewallCommand(
			ctx, "nft", "list", "chain", chain.Family, chain.Table, chain.Name,
		)
		if err != nil {
			return false, err
		}
		for _, rule := range firewallPorts {
			marker := "netpulse-" + rule.protocol + "-" + rule.port + "-" + chain.Hook
			if strings.Contains(chainOutput, marker) {
				continue
			}
			if _, err := runFirewallCommand(
				ctx,
				"nft", "insert", "rule", chain.Family, chain.Table, chain.Name,
				rule.protocol, "dport", rule.port, "accept", "comment", marker,
			); err != nil {
				return false, err
			}
		}
		configured = true
	}
	return configured, nil
}

// configureIPTables 通过 iptables 及可用的 ip6tables 添加幂等双向规则。
//
// 参数:
//   - ctx: 控制 iptables 命令执行的 Context。
//
// 返回值: 全部规则配置成功时返回 nil，否则返回错误。
func configureIPTables(ctx context.Context) error {
	for _, binary := range []string{"iptables", "ip6tables"} {
		if !commandExists(binary) {
			continue
		}
		for _, chain := range []string{"INPUT", "OUTPUT"} {
			for _, rule := range firewallPorts {
				ruleArguments := []string{
					"-p", rule.protocol, "--dport", rule.port, "-j", "ACCEPT",
				}
				if _, err := runFirewallCommand(
					ctx, binary, append([]string{"-C", chain}, ruleArguments...)...,
				); err == nil {
					continue
				}
				if _, err := runFirewallCommand(
					ctx, binary, append([]string{"-I", chain, "1"}, ruleArguments...)...,
				); err != nil {
					return err
				}
			}
		}
	}
	return nil
}

// commandExists 判断系统 PATH 中是否存在指定命令。
//
// 参数:
//   - name: 要查找的命令名。
//
// 返回值: 命令存在时返回 True。
func commandExists(name string) bool {
	_, err := exec.LookPath(name)
	return err == nil
}

// runFirewallCommand 使用英文环境执行防火墙命令并保留失败输出。
//
// 参数:
//   - ctx: 控制命令执行的 Context。
//   - name: 要执行的命令名。
//   - arguments: 命令参数。
//
// 返回值: 命令输出；失败时返回包含命令输出的错误。
func runFirewallCommand(
	ctx context.Context,
	name string,
	arguments ...string,
) (string, error) {
	command := exec.CommandContext(ctx, name, arguments...)
	command.Env = append(os.Environ(), "LC_ALL=C", "LANG=C")
	output, err := command.CombinedOutput()
	text := strings.TrimSpace(string(output))
	if err != nil {
		return text, fmt.Errorf("%s: %s: %w", name, text, err)
	}
	return text, nil
}
