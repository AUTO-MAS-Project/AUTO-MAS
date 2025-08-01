package version

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

func TestParseVersion(t *testing.T) {
	tests := []struct {
		input    string
		expected *ParsedVersion
		hasError bool
	}{
		{"4.4.0.0", &ParsedVersion{4, 4, 0, 0}, false},
		{"4.4.1.3", &ParsedVersion{4, 4, 1, 3}, false},
		{"1.2.3", &ParsedVersion{1, 2, 3, 0}, false},
		{"invalid", nil, true},
		{"1.2", nil, true},
		{"1.2.3.4.5", nil, true},
	}

	for _, test := range tests {
		result, err := ParseVersion(test.input)
		
		if test.hasError {
			if err == nil {
				t.Errorf("Expected error for input %s, but got none", test.input)
			}
			continue
		}
		
		if err != nil {
			t.Errorf("Unexpected error for input %s: %v", test.input, err)
			continue
		}
		
		if result.Major != test.expected.Major ||
			result.Minor != test.expected.Minor ||
			result.Patch != test.expected.Patch ||
			result.Beta != test.expected.Beta {
			t.Errorf("For input %s, expected %+v, got %+v", test.input, test.expected, result)
		}
	}
}

func TestToDisplayVersion(t *testing.T) {
	tests := []struct {
		version  *ParsedVersion
		expected string
	}{
		{&ParsedVersion{4, 4, 0, 0}, "v4.4.0"},
		{&ParsedVersion{4, 4, 1, 3}, "v4.4.1-beta3"},
		{&ParsedVersion{1, 2, 3, 0}, "v1.2.3"},
		{&ParsedVersion{1, 2, 3, 5}, "v1.2.3-beta5"},
	}

	for _, test := range tests {
		result := test.version.ToDisplayVersion()
		if result != test.expected {
			t.Errorf("For version %+v, expected %s, got %s", test.version, test.expected, result)
		}
	}
}

func TestGetChannel(t *testing.T) {
	tests := []struct {
		version  *ParsedVersion
		expected string
	}{
		{&ParsedVersion{4, 4, 0, 0}, "stable"},
		{&ParsedVersion{4, 4, 1, 3}, "beta"},
		{&ParsedVersion{1, 2, 3, 0}, "stable"},
		{&ParsedVersion{1, 2, 3, 1}, "beta"},
	}

	for _, test := range tests {
		result := test.version.GetChannel()
		if result != test.expected {
			t.Errorf("For version %+v, expected channel %s, got %s", test.version, test.expected, result)
		}
	}
}

func TestIsNewer(t *testing.T) {
	tests := []struct {
		v1       *ParsedVersion
		v2       *ParsedVersion
		expected bool
	}{
		{&ParsedVersion{4, 4, 1, 0}, &ParsedVersion{4, 4, 0, 0}, true},
		{&ParsedVersion{4, 4, 0, 0}, &ParsedVersion{4, 4, 1, 0}, false},
		{&ParsedVersion{4, 4, 1, 3}, &ParsedVersion{4, 4, 1, 2}, true},
		{&ParsedVersion{4, 4, 1, 2}, &ParsedVersion{4, 4, 1, 3}, false},
		{&ParsedVersion{4, 4, 1, 0}, &ParsedVersion{4, 4, 1, 0}, false},
	}

	for _, test := range tests {
		result := test.v1.IsNewer(test.v2)
		if result != test.expected {
			t.Errorf("For %+v.IsNewer(%+v), expected %t, got %t", test.v1, test.v2, test.expected, result)
		}
	}
}

func TestLoadVersionFromFile(t *testing.T) {
	// Create a temporary directory
	tempDir, err := os.MkdirTemp("", "version_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	// Create resources directory
	resourcesDir := filepath.Join(tempDir, "resources")
	if err := os.MkdirAll(resourcesDir, 0755); err != nil {
		t.Fatal(err)
	}

	// Create test version file
	versionData := VersionInfo{
		MainVersion: "4.4.1.3",
		VersionInfo: map[string]map[string][]string{
			"4.4.1.3": {
				"修复BUG": {"移除崩溃弹窗机制"},
			},
		},
	}

	data, err := json.Marshal(versionData)
	if err != nil {
		t.Fatal(err)
	}

	versionFile := filepath.Join(resourcesDir, "version.json")
	if err := os.WriteFile(versionFile, data, 0644); err != nil {
		t.Fatal(err)
	}

	// Create version manager with custom executable directory and logger
	vm := NewVersionManager()
	vm.executableDir = tempDir

	// Test loading version
	result, err := vm.LoadVersionFromFile()
	if err != nil {
		t.Fatalf("Failed to load version: %v", err)
	}

	if result.MainVersion != "4.4.1.3" {
		t.Errorf("Expected main version 4.4.1.3, got %s", result.MainVersion)
	}

	if len(result.VersionInfo) != 1 {
		t.Errorf("Expected 1 version info entry, got %d", len(result.VersionInfo))
	}
}

func TestLoadVersionFromFileNotFound(t *testing.T) {
	// Create a temporary directory without version file
	tempDir, err := os.MkdirTemp("", "version_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	// Create version manager with custom executable directory and logger
	vm := NewVersionManager()
	vm.executableDir = tempDir

	// Test loading version (should now return default version instead of error)
	result, err := vm.LoadVersionFromFile()
	if err != nil {
		t.Errorf("Expected no error with fallback mechanism, but got: %v", err)
	}

	// Should return default version
	if result.MainVersion != "0.0.0.0" {
		t.Errorf("Expected default version 0.0.0.0, got %s", result.MainVersion)
	}

	if result.VersionInfo == nil {
		t.Error("Expected initialized VersionInfo map, got nil")
	}
}

func TestLoadVersionWithDefault(t *testing.T) {
	// Create a temporary directory
	tempDir, err := os.MkdirTemp("", "version_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	// Create version manager with custom executable directory
	vm := NewVersionManager()
	vm.executableDir = tempDir

	// Test loading version with default (no file exists)
	result := vm.LoadVersionWithDefault()
	if result == nil {
		t.Fatal("Expected non-nil result from LoadVersionWithDefault")
	}

	if result.MainVersion != "0.0.0.0" {
		t.Errorf("Expected default version 0.0.0.0, got %s", result.MainVersion)
	}

	if result.VersionInfo == nil {
		t.Error("Expected initialized VersionInfo map, got nil")
	}
}

func TestLoadVersionWithDefaultValidFile(t *testing.T) {
	// Create a temporary directory
	tempDir, err := os.MkdirTemp("", "version_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	// Create resources directory
	resourcesDir := filepath.Join(tempDir, "resources")
	if err := os.MkdirAll(resourcesDir, 0755); err != nil {
		t.Fatal(err)
	}

	// Create test version file
	versionData := VersionInfo{
		MainVersion: "4.4.1.3",
		VersionInfo: map[string]map[string][]string{
			"4.4.1.3": {
				"修复BUG": {"移除崩溃弹窗机制"},
			},
		},
	}

	data, err := json.Marshal(versionData)
	if err != nil {
		t.Fatal(err)
	}

	versionFile := filepath.Join(resourcesDir, "version.json")
	if err := os.WriteFile(versionFile, data, 0644); err != nil {
		t.Fatal(err)
	}

	// Create version manager with custom executable directory
	vm := NewVersionManager()
	vm.executableDir = tempDir

	// Test loading version with default (valid file exists)
	result := vm.LoadVersionWithDefault()
	if result == nil {
		t.Fatal("Expected non-nil result from LoadVersionWithDefault")
	}

	if result.MainVersion != "4.4.1.3" {
		t.Errorf("Expected version 4.4.1.3, got %s", result.MainVersion)
	}

	if len(result.VersionInfo) != 1 {
		t.Errorf("Expected 1 version info entry, got %d", len(result.VersionInfo))
	}
}

func TestLoadVersionFromFileCorrupted(t *testing.T) {
	// Create a temporary directory
	tempDir, err := os.MkdirTemp("", "version_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	// Create resources directory
	resourcesDir := filepath.Join(tempDir, "resources")
	if err := os.MkdirAll(resourcesDir, 0755); err != nil {
		t.Fatal(err)
	}

	// Create corrupted version file
	versionFile := filepath.Join(resourcesDir, "version.json")
	if err := os.WriteFile(versionFile, []byte("invalid json content"), 0644); err != nil {
		t.Fatal(err)
	}

	// Create version manager with custom executable directory
	vm := NewVersionManager()
	vm.executableDir = tempDir

	// Test loading version (should return default version for corrupted file)
	result, err := vm.LoadVersionFromFile()
	if err != nil {
		t.Errorf("Expected no error with fallback mechanism for corrupted file, but got: %v", err)
	}

	// Should return default version
	if result.MainVersion != "0.0.0.0" {
		t.Errorf("Expected default version 0.0.0.0 for corrupted file, got %s", result.MainVersion)
	}

	if result.VersionInfo == nil {
		t.Error("Expected initialized VersionInfo map for corrupted file, got nil")
	}
}

func TestLoadVersionWithDefaultCorrupted(t *testing.T) {
	// Create a temporary directory
	tempDir, err := os.MkdirTemp("", "version_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	// Create resources directory
	resourcesDir := filepath.Join(tempDir, "resources")
	if err := os.MkdirAll(resourcesDir, 0755); err != nil {
		t.Fatal(err)
	}

	// Create corrupted version file
	versionFile := filepath.Join(resourcesDir, "version.json")
	if err := os.WriteFile(versionFile, []byte("invalid json content"), 0644); err != nil {
		t.Fatal(err)
	}

	// Create version manager with custom executable directory
	vm := NewVersionManager()
	vm.executableDir = tempDir

	// Test loading version with default (corrupted file)
	result := vm.LoadVersionWithDefault()
	if result == nil {
		t.Fatal("Expected non-nil result from LoadVersionWithDefault for corrupted file")
	}

	if result.MainVersion != "0.0.0.0" {
		t.Errorf("Expected default version 0.0.0.0 for corrupted file, got %s", result.MainVersion)
	}

	if result.VersionInfo == nil {
		t.Error("Expected initialized VersionInfo map for corrupted file, got nil")
	}
}

func TestCreateDefaultVersion(t *testing.T) {
	vm := NewVersionManager()
	
	result := vm.createDefaultVersion()
	if result == nil {
		t.Fatal("Expected non-nil result from createDefaultVersion")
	}

	if result.MainVersion != "0.0.0.0" {
		t.Errorf("Expected default version 0.0.0.0, got %s", result.MainVersion)
	}

	if result.VersionInfo == nil {
		t.Error("Expected initialized VersionInfo map, got nil")
	}

	if len(result.VersionInfo) != 0 {
		t.Errorf("Expected empty VersionInfo map, got %d entries", len(result.VersionInfo))
	}
}