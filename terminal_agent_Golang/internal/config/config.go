// Package config 管理 Agent 的本地 YAML 配置。
package config

import (
	"bytes"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

const fileName = "config.yaml"

// Config 保存 Agent 本地设备标识配置。
type Config struct {
	Device DeviceConfig `yaml:"device"`
}

// DeviceConfig 保存 Agent 本地设备标识。
type DeviceConfig struct {
	DeviceID quotedString `yaml:"device_id"`
}

type quotedString string

// DeviceID 返回去除首尾空白后的设备标识。
//
// 参数: 无。
// 返回值: 当前配置中的 device_id。
func (agentConfig Config) DeviceID() string {
	return strings.TrimSpace(string(agentConfig.Device.DeviceID))
}

// SetDeviceID 更新本地设备标识。
//
// 参数:
//   - deviceID: 设备唯一标识。
//
// 返回值: 无。
func (agentConfig *Config) SetDeviceID(deviceID string) {
	agentConfig.Device.DeviceID = quotedString(deviceID)
}

// ExecutablePath 返回可执行文件同目录下的配置文件路径。
//
// 参数: 无。
// 返回值: 配置文件绝对路径；无法确定可执行文件位置时返回错误。
func ExecutablePath() (string, error) {
	executablePath, err := os.Executable()
	if err != nil {
		return "", fmt.Errorf("获取 Agent 程序路径失败: %w", err)
	}
	resolvedPath, err := filepath.EvalSymlinks(executablePath)
	if err != nil {
		resolvedPath = executablePath
	}
	return filepath.Join(filepath.Dir(resolvedPath), fileName), nil
}

// LoadOrCreate 读取 YAML 配置文件，并在文件不存在时创建空配置。
//
// 参数:
//   - path: 配置文件路径。
//
// 返回值: 配置内容、是否新建配置文件以及处理错误。
func LoadOrCreate(path string) (Config, bool, error) {
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		defaultConfig := Config{}
		if writeErr := Write(path, defaultConfig); writeErr != nil {
			return Config{}, false, writeErr
		}
		return defaultConfig, true, nil
	}
	if err != nil {
		return Config{}, false, fmt.Errorf("读取配置文件失败: %w", err)
	}

	var agentConfig Config
	if err := yaml.Unmarshal(data, &agentConfig); err != nil {
		return Config{}, false, fmt.Errorf("解析配置文件失败: %w", err)
	}
	return agentConfig, false, nil
}

// MarshalYAML 将配置字符串编码为带双引号的 YAML 标量。
//
// 参数: 无。
// 返回值: 使用双引号样式的 YAML Node，以及始终为 nil 的错误。
func (value quotedString) MarshalYAML() (any, error) {
	return &yaml.Node{
		Kind:  yaml.ScalarNode,
		Tag:   "!!str",
		Value: string(value),
		Style: yaml.DoubleQuotedStyle,
	}, nil
}

// Write 将 Agent 配置以 YAML 格式写入指定文件。
//
// 参数:
//   - path: 配置文件路径。
//   - agentConfig: 要保存的配置内容。
//
// 返回值: 保存成功时返回 nil，否则返回写入错误。
func Write(path string, agentConfig Config) error {
	var buffer bytes.Buffer
	encoder := yaml.NewEncoder(&buffer)
	encoder.SetIndent(2)
	if err := encoder.Encode(agentConfig); err != nil {
		return fmt.Errorf("序列化配置文件失败: %w", err)
	}
	if err := encoder.Close(); err != nil {
		return fmt.Errorf("关闭 YAML Encoder 失败: %w", err)
	}
	if err := os.WriteFile(path, buffer.Bytes(), 0o600); err != nil {
		return fmt.Errorf("写入配置文件失败: %w", err)
	}
	return nil
}
