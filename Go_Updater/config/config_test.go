package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestEncryptDecryptCDK(t *testing.T) {
	tests := []struct {
		name     string
		original string
	}{
		{
			name:     "Empty CDK",
			original: "",
		},
		{
			name:     "Simple CDK",
			original: "test123",
		},
		{
			name:     "Complex CDK",
			original: "ABC123-DEF456-GHI789",
		},
		{
			name:     "CDK with special characters",
			original: "test@#$%^&*()_+-={}[]|\\:;\"'<>?,./",
		},
		{
			name:     "Long CDK",
			original: "this-is-a-very-long-cdk-key-that-should-still-work-properly-with-encryption-and-decryption",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			// Test encryption
			encrypted := encryptCDK(tt.original)

			// Empty string should remain empty
			if tt.original == "" {
				if encrypted != "" {
					t.Errorf("Expected empty string for empty input, got %s", encrypted)
				}
				return
			}

			// Encrypted should be different from original (unless original is empty)
			if encrypted == tt.original {
				t.Errorf("Encrypted CDK should be different from original")
			}

			// Test decryption
			decrypted, err := decryptCDK(encrypted)
			if err != nil {
				t.Errorf("Decryption failed: %v", err)
			}

			// Decrypted should match original
			if decrypted != tt.original {
				t.Errorf("Expected %s, got %s", tt.original, decrypted)
			}
		})
	}
}

func TestConfigSetGetCDK(t *testing.T) {
	config := &Config{}

	testCDK := "test-cdk-123"

	// Set CDK (should encrypt)
	config.SetCDK(testCDK)

	// CDK field should be encrypted (different from original)
	if config.CDK == testCDK {
		t.Errorf("CDK should be encrypted in config")
	}

	// Get CDK (should decrypt)
	retrievedCDK, err := config.GetCDK()
	if err != nil {
		t.Errorf("Failed to get CDK: %v", err)
	}

	if retrievedCDK != testCDK {
		t.Errorf("Expected %s, got %s", testCDK, retrievedCDK)
	}
}

func TestDecryptInvalidCDK(t *testing.T) {
	// Test with invalid base64
	_, err := decryptCDK("invalid-base64!")
	if err == nil {
		t.Errorf("Expected error for invalid base64")
	}
}

func TestConfigManagerLoadSave(t *testing.T) {
	// Create temporary directory for test
	tempDir := t.TempDir()

	// Create config manager with temp path
	cm := &DefaultConfigManager{
		configPath: filepath.Join(tempDir, "test-config.yaml"),
	}

	// Test loading non-existent config (should create default)
	config, err := cm.Load()
	if err != nil {
		t.Errorf("Failed to load config: %v", err)
	}

	if config == nil {
		t.Errorf("Config should not be nil")
	}

	// Verify default values
	if config.CurrentVersion != "v1.0.0" {
		t.Errorf("Expected default version v1.0.0, got %s", config.CurrentVersion)
	}

	if config.UserAgent != "LightweightUpdater/1.0" {
		t.Errorf("Expected default user agent, got %s", config.UserAgent)
	}

	// Set some values including CDK
	config.ResourceID = "TEST123"
	config.SetCDK("secret-cdk-key")

	// Save config
	err = cm.Save(config)
	if err != nil {
		t.Errorf("Failed to save config: %v", err)
	}

	// Load config again
	loadedConfig, err := cm.Load()
	if err != nil {
		t.Errorf("Failed to load saved config: %v", err)
	}

	// Verify values
	if loadedConfig.ResourceID != "TEST123" {
		t.Errorf("Expected ResourceID TEST123, got %s", loadedConfig.ResourceID)
	}

	// Verify CDK is properly encrypted/decrypted
	retrievedCDK, err := loadedConfig.GetCDK()
	if err != nil {
		t.Errorf("Failed to get CDK from loaded config: %v", err)
	}

	if retrievedCDK != "secret-cdk-key" {
		t.Errorf("Expected CDK secret-cdk-key, got %s", retrievedCDK)
	}

	// Verify CDK is encrypted in the config struct
	if loadedConfig.CDK == "secret-cdk-key" {
		t.Errorf("CDK should be encrypted in config file")
	}
}

func TestConfigValidation(t *testing.T) {
	tests := []struct {
		name        string
		config      *Config
		expectError bool
	}{
		{
			name:        "Nil config",
			config:      nil,
			expectError: true,
		},
		{
			name: "Empty ResourceID",
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
			name: "Empty CurrentVersion",
			config: &Config{
				ResourceID:     "TEST",
				CurrentVersion: "",
				UserAgent:      "Test/1.0",
				LogLevel:       "info",
				CheckInterval:  3600,
			},
			expectError: true,
		},
		{
			name: "Invalid LogLevel",
			config: &Config{
				ResourceID:     "TEST",
				CurrentVersion: "v1.0.0",
				UserAgent:      "Test/1.0",
				LogLevel:       "invalid",
				CheckInterval:  3600,
			},
			expectError: true,
		},
		{
			name: "Invalid CheckInterval",
			config: &Config{
				ResourceID:     "TEST",
				CurrentVersion: "v1.0.0",
				UserAgent:      "Test/1.0",
				LogLevel:       "info",
				CheckInterval:  30, // Less than 60
			},
			expectError: true,
		},
		{
			name: "Valid config",
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
				t.Errorf("Expected error but got none")
			}
			if !tt.expectError && err != nil {
				t.Errorf("Expected no error but got: %v", err)
			}
		})
	}
}

func TestGetConfigDir(t *testing.T) {
	// Save original APPDATA
	originalAppData := os.Getenv("APPDATA")
	defer os.Setenv("APPDATA", originalAppData)

	// Test with APPDATA set
	os.Setenv("APPDATA", "C:\\Users\\Test\\AppData\\Roaming")
	dir := getConfigDir()
	expected := "C:\\Users\\Test\\AppData\\Roaming\\LightweightUpdater"
	if dir != expected {
		t.Errorf("Expected %s, got %s", expected, dir)
	}

	// Test without APPDATA
	os.Unsetenv("APPDATA")
	dir = getConfigDir()
	if dir != "." {
		t.Errorf("Expected current directory, got %s", dir)
	}
}

func TestValidateAndApplyDefaults(t *testing.T) {
	tests := []struct {
		name     string
		input    *Config
		expected *Config
		hasError bool
	}{
		{
			name: "Apply defaults to empty config",
			input: &Config{
				ResourceID: "TEST",
			},
			expected: &Config{
				ResourceID:     "TEST",
				CurrentVersion: "v1.0.0",
				UserAgent:      "LightweightUpdater/1.0",
				LogLevel:       "info",
				CheckInterval:  3600,
			},
			hasError: false,
		},
		{
			name: "Partial config with some defaults needed",
			input: &Config{
				ResourceID:     "TEST",
				CurrentVersion: "v2.0.0",
				LogLevel:       "debug",
			},
			expected: &Config{
				ResourceID:     "TEST",
				CurrentVersion: "v2.0.0",
				UserAgent:      "LightweightUpdater/1.0",
				LogLevel:       "debug",
				CheckInterval:  3600,
			},
			hasError: false,
		},
		{
			name: "Config with invalid values after defaults",
			input: &Config{
				ResourceID:    "", // Invalid - empty
				CheckInterval: 30, // Invalid - too small
			},
			expected: nil,
			hasError: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			err := validateAndApplyDefaults(tt.input)

			if tt.hasError {
				if err == nil {
					t.Errorf("Expected error but got none")
				}
				return
			}

			if err != nil {
				t.Errorf("Unexpected error: %v", err)
				return
			}

			// Check that defaults were applied correctly
			if tt.input.CurrentVersion != tt.expected.CurrentVersion {
				t.Errorf("CurrentVersion: expected %s, got %s", tt.expected.CurrentVersion, tt.input.CurrentVersion)
			}
			if tt.input.UserAgent != tt.expected.UserAgent {
				t.Errorf("UserAgent: expected %s, got %s", tt.expected.UserAgent, tt.input.UserAgent)
			}
			if tt.input.LogLevel != tt.expected.LogLevel {
				t.Errorf("LogLevel: expected %s, got %s", tt.expected.LogLevel, tt.input.LogLevel)
			}
			if tt.input.CheckInterval != tt.expected.CheckInterval {
				t.Errorf("CheckInterval: expected %d, got %d", tt.expected.CheckInterval, tt.input.CheckInterval)
			}
		})
	}
}

func TestGetDefaultConfig(t *testing.T) {
	config := getDefaultConfig()

	if config == nil {
		t.Fatal("getDefaultConfig() returned nil")
	}

	// Verify default values
	if config.ResourceID != "PLACEHOLDER" {
		t.Errorf("Expected ResourceID 'PLACEHOLDER', got %s", config.ResourceID)
	}
	if config.CurrentVersion != "v1.0.0" {
		t.Errorf("Expected CurrentVersion 'v1.0.0', got %s", config.CurrentVersion)
	}
	if config.UserAgent != "LightweightUpdater/1.0" {
		t.Errorf("Expected UserAgent 'LightweightUpdater/1.0', got %s", config.UserAgent)
	}
	if config.LogLevel != "info" {
		t.Errorf("Expected LogLevel 'info', got %s", config.LogLevel)
	}
	if config.CheckInterval != 3600 {
		t.Errorf("Expected CheckInterval 3600, got %d", config.CheckInterval)
	}
	if !config.AutoCheck {
		t.Errorf("Expected AutoCheck true, got %v", config.AutoCheck)
	}
}

func TestConfigManagerWithCustomPath(t *testing.T) {
	tempDir := t.TempDir()
	customPath := filepath.Join(tempDir, "custom-config.yaml")

	cm := &DefaultConfigManager{
		configPath: customPath,
	}

	// Test GetConfigPath
	if cm.GetConfigPath() != customPath {
		t.Errorf("Expected config path %s, got %s", customPath, cm.GetConfigPath())
	}

	// Test Save and Load with custom path
	testConfig := &Config{
		ResourceID:     "CUSTOM",
		CurrentVersion: "v1.5.0",
		UserAgent:      "CustomUpdater/1.0",
		LogLevel:       "debug",
		CheckInterval:  7200,
		AutoCheck:      false,
	}

	// Save config
	err := cm.Save(testConfig)
	if err != nil {
		t.Fatalf("Failed to save config: %v", err)
	}

	// Load config
	loadedConfig, err := cm.Load()
	if err != nil {
		t.Fatalf("Failed to load config: %v", err)
	}

	// Verify loaded config matches saved config
	if loadedConfig.ResourceID != testConfig.ResourceID {
		t.Errorf("ResourceID mismatch: expected %s, got %s", testConfig.ResourceID, loadedConfig.ResourceID)
	}
	if loadedConfig.CurrentVersion != testConfig.CurrentVersion {
		t.Errorf("CurrentVersion mismatch: expected %s, got %s", testConfig.CurrentVersion, loadedConfig.CurrentVersion)
	}
	if loadedConfig.AutoCheck != testConfig.AutoCheck {
		t.Errorf("AutoCheck mismatch: expected %v, got %v", testConfig.AutoCheck, loadedConfig.AutoCheck)
	}
}

func TestConfigManagerErrorHandling(t *testing.T) {
	// Test with invalid directory path
	invalidPath := string([]byte{0}) + "/invalid/config.yaml"
	cm := &DefaultConfigManager{
		configPath: invalidPath,
	}

	// Load should fail with invalid path
	_, err := cm.Load()
	if err == nil {
		t.Error("Expected error when loading from invalid path")
	}

	// Save should fail with invalid path
	testConfig := getDefaultConfig()
	testConfig.ResourceID = "TEST"
	err = cm.Save(testConfig)
	if err == nil {
		t.Error("Expected error when saving to invalid path")
	}
}

func TestEncryptDecryptEdgeCases(t *testing.T) {
	tests := []struct {
		name  string
		input string
	}{
		{"Unicode characters", "测试CDK密钥🔑"},
		{"Very long string", strings.Repeat("A", 1000)},
		{"Binary-like data", string([]byte{0, 1, 2, 3, 255, 254, 253})},
		{"Only spaces", "   "},
		{"Newlines and tabs", "line1\nline2\tindented"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			encrypted := encryptCDK(tt.input)
			decrypted, err := decryptCDK(encrypted)

			if err != nil {
				t.Errorf("Decryption failed: %v", err)
			}

			if decrypted != tt.input {
				t.Errorf("Encryption/decryption mismatch: expected %q, got %q", tt.input, decrypted)
			}
		})
	}
}
