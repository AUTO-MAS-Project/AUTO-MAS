package assets

import (
	"testing"
)

func TestGetConfigTemplate(t *testing.T) {
	data, err := GetConfigTemplate()
	if err != nil {
		t.Fatalf("Failed to get config template: %v", err)
	}

	if len(data) == 0 {
		t.Fatal("Config template is empty")
	}

	// Check that it contains expected content
	content := string(data)
	if !contains(content, "resource_id") {
		t.Error("Config template should contain 'resource_id'")
	}

	if !contains(content, "current_version") {
		t.Error("Config template should contain 'current_version'")
	}

	if !contains(content, "user_agent") {
		t.Error("Config template should contain 'user_agent'")
	}
}

func TestListAssets(t *testing.T) {
	assets, err := ListAssets()
	if err != nil {
		t.Fatalf("Failed to list assets: %v", err)
	}

	if len(assets) == 0 {
		t.Fatal("No assets found")
	}

	// Check that config template is in the list
	found := false
	for _, asset := range assets {
		if asset == "config_template.yaml" {
			found = true
			break
		}
	}

	if !found {
		t.Error("config_template.yaml should be in the assets list")
	}
}

func TestGetAssetFS(t *testing.T) {
	fs := GetAssetFS()
	if fs == nil {
		t.Fatal("Asset filesystem should not be nil")
	}

	// Try to open the config template
	file, err := fs.Open("config_template.yaml")
	if err != nil {
		t.Fatalf("Failed to open config template from filesystem: %v", err)
	}
	defer file.Close()

	// Check that we can read from it
	buffer := make([]byte, 100)
	n, err := file.Read(buffer)
	if err != nil && err.Error() != "EOF" {
		t.Fatalf("Failed to read from config template: %v", err)
	}

	if n == 0 {
		t.Fatal("Config template appears to be empty")
	}
}

// Helper function to check if string contains substring
func contains(s, substr string) bool {
	return len(s) >= len(substr) && (s == substr || len(substr) == 0 ||
		(len(s) > len(substr) && (s[:len(substr)] == substr ||
			s[len(s)-len(substr):] == substr ||
			containsAt(s, substr, 1))))
}

func containsAt(s, substr string, start int) bool {
	if start >= len(s) {
		return false
	}
	if start+len(substr) > len(s) {
		return containsAt(s, substr, start+1)
	}
	if s[start:start+len(substr)] == substr {
		return true
	}
	return containsAt(s, substr, start+1)
}
