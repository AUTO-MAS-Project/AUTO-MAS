package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestConfigManagerLoadSave(t *testing.T) {
	// 为测试创建临时目录
	tempDir := t.TempDir()

	// 使用临时路径创建配置管理器
	cm := &DefaultConfigManager{
		configPath: filepath.Join(tempDir, "test-config.yaml"),
	}

	// 测试加载不存在的配置（应创建默认配置）
	config, err := cm.Load()
	if err != nil {
		t.Errorf("加载配置失败: %v", err)
	}

	if config == nil {
		t.Errorf("配置不应为 nil")
	}

	// 验证默认值
	if config.CurrentVersion != "v1.0.0" {
		t.Errorf("期望默认版本 v1.0.0，得到 %s", config.CurrentVersion)
	}

	if config.UserAgent != "AUTO_MAA_Go_Updater/1.0" {
		t.Errorf("期望默认用户代理，得到 %s", config.UserAgent)
	}

	// 设置一些值
	config.ResourceID = "TEST123"

	// 保存配置
	err = cm.Save(config)
	if err != nil {
		t.Errorf("保存配置失败: %v", err)
	}

	// 再次加载配置
	loadedConfig, err := cm.Load()
	if err != nil {
		t.Errorf("加载已保存配置失败: %v", err)
	}

	// 验证值
	if loadedConfig.ResourceID != "TEST123" {
		t.Errorf("期望 ResourceID TEST123，得到 %s", loadedConfig.ResourceID)
	}
}

func TestConfigValidation(t *testing.T) {
	tests := []struct {
		name        string
		config      *Config
		expectError bool
	}{
		{
			name:        "空配置",
			config:      nil,
			expectError: true,
		},
		{
			name: "空 ResourceID",
			config: &Config{
				ResourceID:     "",
				CurrentVersion: "v1.0.0",
				UserAgent:      "Test/1.0",
				LogLevel:       "info",
				CheckInterval:  3600,
			},
			expectError: true,
		},
		{
			name: "有效配置",
			config: &Config{
				ResourceID:     "TEST",
				CurrentVersion: "v1.0.0",
				UserAgent:      "Test/1.0",
				LogLevel:       "info",
				CheckInterval:  3600,
			},
			expectError: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateConfig(tt.config)
			if tt.expectError && err == nil {
				t.Errorf("期望错误但没有得到")
			}
			if !tt.expectError && err != nil {
				t.Errorf("期望无错误但得到: %v", err)
			}
		})
	}
}

func TestGetDefaultConfig(t *testing.T) {
	config := getDefaultConfig()

	if config == nil {
		t.Fatal("getDefaultConfig() 返回 nil")
	}

	// 验证默认值
	if config.ResourceID != "AUTO_MAA" {
		t.Errorf("期望 ResourceID 'AUTO_MAA'，得到 %s", config.ResourceID)
	}
	if config.CurrentVersion != "v1.0.0" {
		t.Errorf("期望 CurrentVersion 'v1.0.0'，得到 %s", config.CurrentVersion)
	}
	if config.UserAgent != "AUTO_MAA_Go_Updater/1.0" {
		t.Errorf("期望 UserAgent 'AUTO_MAA_Go_Updater/1.0'，得到 %s", config.UserAgent)
	}
	if config.LogLevel != "info" {
		t.Errorf("期望 LogLevel 'info'，得到 %s", config.LogLevel)
	}
	if config.CheckInterval != 3600 {
		t.Errorf("期望 CheckInterval 3600，得到 %d", config.CheckInterval)
	}
	if !config.AutoCheck {
		t.Errorf("期望 AutoCheck true，得到 %v", config.AutoCheck)
	}
}

func TestGetConfigDir(t *testing.T) {
	// 保存原始 APPDATA
	originalAppData := os.Getenv("APPDATA")
	defer os.Setenv("APPDATA", originalAppData)

	// 测试设置了 APPDATA
	os.Setenv("APPDATA", "C:\\Users\\Test\\AppData\\Roaming")
	dir := getConfigDir()
	expected := "C:\\Users\\Test\\AppData\\Roaming\\AUTO_MAA_Go_Updater"
	if dir != expected {
		t.Errorf("期望 %s，得到 %s", expected, dir)
	}

	// 测试没有 APPDATA
	os.Unsetenv("APPDATA")
	dir = getConfigDir()
	if dir != "." {
		t.Errorf("期望当前目录，得到 %s", dir)
	}
}
