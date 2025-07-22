package config

import (
	"fmt"
	"os"
	"path/filepath"

	"AUTO_MAA_Go_Updater/assets"
	"gopkg.in/yaml.v3"
)

// Config 表示应用程序配置
type Config struct {
	ResourceID     string `yaml:"resource_id"`
	CurrentVersion string `yaml:"current_version"`
	UserAgent      string `yaml:"user_agent"`
	BackupURL      string `yaml:"backup_url"`
	LogLevel       string `yaml:"log_level"`
	AutoCheck      bool   `yaml:"auto_check"`
	CheckInterval  int    `yaml:"check_interval"` // 秒
}

// ConfigManager 定义配置管理的接口方法
type ConfigManager interface {
	Load() (*Config, error)
	Save(config *Config) error
	GetConfigPath() string
}

// DefaultConfigManager 实现 ConfigManager 接口
type DefaultConfigManager struct {
	configPath string
}

// NewConfigManager 创建新的配置管理器
func NewConfigManager() ConfigManager {
	configDir := getConfigDir()
	configPath := filepath.Join(configDir, "config.yaml")
	return &DefaultConfigManager{
		configPath: configPath,
	}
}

// GetConfigPath 返回配置文件的路径
func (cm *DefaultConfigManager) GetConfigPath() string {
	return cm.configPath
}

// Load 读取并解析配置文件
func (cm *DefaultConfigManager) Load() (*Config, error) {
	// 如果配置目录不存在则创建
	configDir := filepath.Dir(cm.configPath)
	if err := os.MkdirAll(configDir, 0755); err != nil {
		return nil, fmt.Errorf("创建配置目录失败: %w", err)
	}

	// 如果配置文件不存在，创建默认配置
	if _, err := os.Stat(cm.configPath); os.IsNotExist(err) {
		defaultConfig := getDefaultConfig()
		if err := cm.Save(defaultConfig); err != nil {
			return nil, fmt.Errorf("创建默认配置失败: %w", err)
		}
		return defaultConfig, nil
	}

	// 读取现有配置文件
	data, err := os.ReadFile(cm.configPath)
	if err != nil {
		return nil, fmt.Errorf("读取配置文件失败: %w", err)
	}

	var config Config
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("解析配置文件失败: %w", err)
	}

	// 验证并应用缺失字段的默认值
	if err := validateAndApplyDefaults(&config); err != nil {
		return nil, fmt.Errorf("配置验证失败: %w", err)
	}

	return &config, nil
}

// Save 将配置写入文件
func (cm *DefaultConfigManager) Save(config *Config) error {
	// 保存前验证配置
	if err := validateConfig(config); err != nil {
		return fmt.Errorf("配置验证失败: %w", err)
	}

	// 如果配置目录不存在则创建
	configDir := filepath.Dir(cm.configPath)
	if err := os.MkdirAll(configDir, 0755); err != nil {
		return fmt.Errorf("创建配置目录失败: %w", err)
	}

	// 将配置序列化为 YAML
	data, err := yaml.Marshal(config)
	if err != nil {
		return fmt.Errorf("序列化配置失败: %w", err)
	}

	// 写入文件
	if err := os.WriteFile(cm.configPath, data, 0644); err != nil {
		return fmt.Errorf("写入配置文件失败: %w", err)
	}

	return nil
}

// getDefaultConfig 返回带有默认值的配置
func getDefaultConfig() *Config {
	// 首先尝试从嵌入模板加载
	if templateData, err := assets.GetConfigTemplate(); err == nil {
		var config Config
		if err := yaml.Unmarshal(templateData, &config); err == nil {
			return &config
		}
	}

	// 如果模板加载失败则回退到硬编码默认值
	return &Config{
		ResourceID:     "M9A", // 默认资源 ID
		CurrentVersion: "v1.0.0",
		UserAgent:      "AUTO_MAA_Go_Updater/1.0",
		BackupURL:      "",
		LogLevel:       "info",
		AutoCheck:      true,
		CheckInterval:  3600, // 1 小时
	}
}

// validateConfig 验证配置值
func validateConfig(config *Config) error {
	if config == nil {
		return fmt.Errorf("配置不能为空")
	}

	if config.ResourceID == "" {
		return fmt.Errorf("resource_id 不能为空")
	}

	if config.CurrentVersion == "" {
		return fmt.Errorf("current_version 不能为空")
	}

	if config.UserAgent == "" {
		return fmt.Errorf("user_agent 不能为空")
	}

	validLogLevels := map[string]bool{
		"debug": true,
		"info":  true,
		"warn":  true,
		"error": true,
	}
	if !validLogLevels[config.LogLevel] {
		return fmt.Errorf("无效的 log_level: %s (必须是 debug, info, warn 或 error)", config.LogLevel)
	}

	if config.CheckInterval < 60 {
		return fmt.Errorf("check_interval 必须至少为 60 秒")
	}

	return nil
}

// validateAndApplyDefaults 验证配置并为缺失字段应用默认值
func validateAndApplyDefaults(config *Config) error {
	defaults := getDefaultConfig()

	// 为空字段应用默认值
	if config.UserAgent == "" {
		config.UserAgent = defaults.UserAgent
	}
	if config.LogLevel == "" {
		config.LogLevel = defaults.LogLevel
	}
	if config.CheckInterval == 0 {
		config.CheckInterval = defaults.CheckInterval
	}
	if config.CurrentVersion == "" {
		config.CurrentVersion = defaults.CurrentVersion
	}

	// 应用默认值后进行验证
	return validateConfig(config)
}

// getConfigDir 返回配置目录路径
func getConfigDir() string {
	// 在 Windows 上使用 APPDATA，回退到当前目录
	if appData := os.Getenv("APPDATA"); appData != "" {
		return filepath.Join(appData, "AUTO_MAA_Go_Updater")
	}
	return "."
}
