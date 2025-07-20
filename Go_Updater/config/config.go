package config

import (
	"encoding/base64"
	"fmt"
	"os"
	"path/filepath"

	"gopkg.in/yaml.v3"
	"lightweight-updater/assets"
)

// Config represents the application configuration
type Config struct {
	ResourceID     string `yaml:"resource_id"`
	CurrentVersion string `yaml:"current_version"`
	CDK            string `yaml:"cdk,omitempty"`
	UserAgent      string `yaml:"user_agent"`
	BackupURL      string `yaml:"backup_url"`
	LogLevel       string `yaml:"log_level"`
	AutoCheck      bool   `yaml:"auto_check"`
	CheckInterval  int    `yaml:"check_interval"` // seconds
}

// ConfigManager interface defines methods for configuration management
type ConfigManager interface {
	Load() (*Config, error)
	Save(config *Config) error
	GetConfigPath() string
}

// DefaultConfigManager implements ConfigManager interface
type DefaultConfigManager struct {
	configPath string
}

// NewConfigManager creates a new configuration manager
func NewConfigManager() ConfigManager {
	configDir := getConfigDir()
	configPath := filepath.Join(configDir, "config.yaml")
	return &DefaultConfigManager{
		configPath: configPath,
	}
}

// GetConfigPath returns the path to the configuration file
func (cm *DefaultConfigManager) GetConfigPath() string {
	return cm.configPath
}

// Load reads and parses the configuration file
func (cm *DefaultConfigManager) Load() (*Config, error) {
	// Create config directory if it doesn't exist
	configDir := filepath.Dir(cm.configPath)
	if err := os.MkdirAll(configDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create config directory: %w", err)
	}

	// If config file doesn't exist, create default config
	if _, err := os.Stat(cm.configPath); os.IsNotExist(err) {
		defaultConfig := getDefaultConfig()
		if err := cm.Save(defaultConfig); err != nil {
			return nil, fmt.Errorf("failed to create default config: %w", err)
		}
		return defaultConfig, nil
	}

	// Read existing config file
	data, err := os.ReadFile(cm.configPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read config file: %w", err)
	}

	var config Config
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("failed to parse config file: %w", err)
	}

	// Validate and apply defaults for missing fields
	if err := validateAndApplyDefaults(&config); err != nil {
		return nil, fmt.Errorf("config validation failed: %w", err)
	}

	return &config, nil
}

// Save writes the configuration to file
func (cm *DefaultConfigManager) Save(config *Config) error {
	// Validate config before saving
	if err := validateConfig(config); err != nil {
		return fmt.Errorf("config validation failed: %w", err)
	}

	// Create config directory if it doesn't exist
	configDir := filepath.Dir(cm.configPath)
	if err := os.MkdirAll(configDir, 0755); err != nil {
		return fmt.Errorf("failed to create config directory: %w", err)
	}

	// Marshal config to YAML
	data, err := yaml.Marshal(config)
	if err != nil {
		return fmt.Errorf("failed to marshal config: %w", err)
	}

	// Write to file
	if err := os.WriteFile(cm.configPath, data, 0644); err != nil {
		return fmt.Errorf("failed to write config file: %w", err)
	}

	return nil
}

// getDefaultConfig returns a configuration with default values
func getDefaultConfig() *Config {
	// Try to load from embedded template first
	if templateData, err := assets.GetConfigTemplate(); err == nil {
		var config Config
		if err := yaml.Unmarshal(templateData, &config); err == nil {
			return &config
		}
	}

	// Fallback to hardcoded defaults if template loading fails
	return &Config{
		ResourceID:     "M9A", // Default resource ID
		CurrentVersion: "v1.0.0",
		CDK:            "",
		UserAgent:      "LightweightUpdater/1.0",
		BackupURL:      "",
		LogLevel:       "info",
		AutoCheck:      true,
		CheckInterval:  3600, // 1 hour
	}
}

// validateConfig validates the configuration values
func validateConfig(config *Config) error {
	if config == nil {
		return fmt.Errorf("config cannot be nil")
	}

	if config.ResourceID == "" {
		return fmt.Errorf("resource_id cannot be empty")
	}

	if config.CurrentVersion == "" {
		return fmt.Errorf("current_version cannot be empty")
	}

	if config.UserAgent == "" {
		return fmt.Errorf("user_agent cannot be empty")
	}

	validLogLevels := map[string]bool{
		"debug": true,
		"info":  true,
		"warn":  true,
		"error": true,
	}
	if !validLogLevels[config.LogLevel] {
		return fmt.Errorf("invalid log_level: %s (must be debug, info, warn, or error)", config.LogLevel)
	}

	if config.CheckInterval < 60 {
		return fmt.Errorf("check_interval must be at least 60 seconds")
	}

	return nil
}

// validateAndApplyDefaults validates config and applies defaults for missing fields
func validateAndApplyDefaults(config *Config) error {
	defaults := getDefaultConfig()

	// Apply defaults for empty fields
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

	// Validate after applying defaults
	return validateConfig(config)
}

// getConfigDir returns the configuration directory path
func getConfigDir() string {
	// Use APPDATA on Windows, fallback to current directory
	if appData := os.Getenv("APPDATA"); appData != "" {
		return filepath.Join(appData, "LightweightUpdater")
	}
	return "."
}

// encryptCDK encrypts the CDK using XOR encryption with a static key
func encryptCDK(cdk string) string {
	if cdk == "" {
		return ""
	}

	key := []byte("updater-key-2024")
	encrypted := make([]byte, len(cdk))

	for i, b := range []byte(cdk) {
		encrypted[i] = b ^ key[i%len(key)]
	}

	return base64.StdEncoding.EncodeToString(encrypted)
}

// decryptCDK decrypts the CDK using XOR decryption with a static key
func decryptCDK(encryptedCDK string) (string, error) {
	if encryptedCDK == "" {
		return "", nil
	}

	encrypted, err := base64.StdEncoding.DecodeString(encryptedCDK)
	if err != nil {
		return "", fmt.Errorf("failed to decode encrypted CDK: %w", err)
	}

	key := []byte("updater-key-2024")
	decrypted := make([]byte, len(encrypted))

	for i, b := range encrypted {
		decrypted[i] = b ^ key[i%len(key)]
	}

	return string(decrypted), nil
}

// SetCDK sets the CDK in the config with encryption
func (c *Config) SetCDK(cdk string) {
	c.CDK = encryptCDK(cdk)
}

// GetCDK returns the decrypted CDK from the config
func (c *Config) GetCDK() (string, error) {
	return decryptCDK(c.CDK)
}
