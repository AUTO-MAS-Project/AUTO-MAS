package api

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestNewClient(t *testing.T) {
	client := NewClient()
	if client == nil {
		t.Fatal("NewClient() returned nil")
	}
	if client.httpClient == nil {
		t.Fatal("HTTP client is nil")
	}
	if client.baseURL != "https://mirrorchyan.com/api/resources" {
		t.Errorf("Expected base URL 'https://mirrorchyan.com/api/resources', got '%s'", client.baseURL)
	}
}

func TestGetOfficialDownloadURL(t *testing.T) {
	client := NewClient()
	
	tests := []struct {
		versionName string
		expected    string
	}{
		{"v4.4.0", "http://221.236.27.82:10197/d/AUTO_MAA/AUTO_MAA_v4.4.0.zip"},
		{"v4.4.1-beta3", "http://221.236.27.82:10197/d/AUTO_MAA/AUTO_MAA_v4.4.1-beta.3.zip"},
		{"v1.2.3", "http://221.236.27.82:10197/d/AUTO_MAA/AUTO_MAA_v1.2.3.zip"},
		{"v1.2.3-beta1", "http://221.236.27.82:10197/d/AUTO_MAA/AUTO_MAA_v1.2.3-beta.1.zip"},
	}

	for _, test := range tests {
		result := client.GetOfficialDownloadURL(test.versionName)
		if result != test.expected {
			t.Errorf("For version %s, expected %s, got %s", test.versionName, test.expected, result)
		}
	}
}

func TestNormalizeVersionForComparison(t *testing.T) {
	client := NewClient()
	
	tests := []struct {
		input    string
		expected string
	}{
		{"4.4.0.0", "v4.4.0"},
		{"4.4.1.3", "v4.4.1-beta3"},
		{"v4.4.0", "v4.4.0"},
		{"v4.4.1-beta3", "v4.4.1-beta3"},
		{"1.2.3", "1.2.3"}, // Not 4-part version, return as-is
	}

	for _, test := range tests {
		result := client.normalizeVersionForComparison(test.input)
		if result != test.expected {
			t.Errorf("For input %s, expected %s, got %s", test.input, test.expected, result)
		}
	}
}

func TestCheckUpdate(t *testing.T) {
	// Create test server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify request parameters
		if r.URL.Query().Get("current_version") != "4.4.0.0" {
			t.Errorf("Expected current_version=4.4.0.0, got %s", r.URL.Query().Get("current_version"))
		}
		if r.URL.Query().Get("channel") != "stable" {
			t.Errorf("Expected channel=stable, got %s", r.URL.Query().Get("channel"))
		}

		// Return mock response
		response := MirrorResponse{
			Code: 0,
			Msg:  "success",
			Data: struct {
				VersionName     string `json:"version_name"`
				VersionNumber   int    `json:"version_number"`
				URL             string `json:"url,omitempty"`
				SHA256          string `json:"sha256,omitempty"`
				Channel         string `json:"channel"`
				OS              string `json:"os"`
				Arch            string `json:"arch"`
				UpdateType      string `json:"update_type,omitempty"`
				ReleaseNote     string `json:"release_note"`
				FileSize        int64  `json:"filesize,omitempty"`
				CDKExpiredTime  int64  `json:"cdk_expired_time,omitempty"`
			}{
				VersionName:   "v4.4.1",
				VersionNumber: 48,
				Channel:       "stable",
				OS:            "",
				Arch:          "",
				ReleaseNote:   "Test release notes",
			},
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(response)
	}))
	defer server.Close()

	// Create client with test server URL
	client := &Client{
		httpClient: &http.Client{},
		baseURL:    server.URL,
	}

	// Test update check
	params := UpdateCheckParams{
		ResourceID:     "AUTO_MAA",
		CurrentVersion: "4.4.0.0",
		Channel:        "stable",
		CDK:            "",
		UserAgent:      "TestAgent/1.0",
	}

	response, err := client.CheckUpdate(params)
	if err != nil {
		t.Fatalf("CheckUpdate failed: %v", err)
	}

	if response.Code != 0 {
		t.Errorf("Expected code 0, got %d", response.Code)
	}
	if response.Data.VersionName != "v4.4.1" {
		t.Errorf("Expected version v4.4.1, got %s", response.Data.VersionName)
	}
	if response.Data.Channel != "stable" {
		t.Errorf("Expected channel stable, got %s", response.Data.Channel)
	}
}

func TestCheckUpdateWithCDK(t *testing.T) {
	// Create test server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		// Verify CDK parameter
		if r.URL.Query().Get("cdk") != "test_cdk_123" {
			t.Errorf("Expected cdk=test_cdk_123, got %s", r.URL.Query().Get("cdk"))
		}

		// Return mock response with CDK download URL
		response := MirrorResponse{
			Code: 0,
			Msg:  "success",
			Data: struct {
				VersionName     string `json:"version_name"`
				VersionNumber   int    `json:"version_number"`
				URL             string `json:"url,omitempty"`
				SHA256          string `json:"sha256,omitempty"`
				Channel         string `json:"channel"`
				OS              string `json:"os"`
				Arch            string `json:"arch"`
				UpdateType      string `json:"update_type,omitempty"`
				ReleaseNote     string `json:"release_note"`
				FileSize        int64  `json:"filesize,omitempty"`
				CDKExpiredTime  int64  `json:"cdk_expired_time,omitempty"`
			}{
				VersionName:    "v4.4.1",
				VersionNumber:  48,
				URL:            "https://mirrorchyan.com/api/resources/download/test123",
				SHA256:         "abcd1234",
				Channel:        "stable",
				OS:             "",
				Arch:           "",
				UpdateType:     "full",
				ReleaseNote:    "Test release notes",
				FileSize:       12345678,
				CDKExpiredTime: 1776013593,
			},
		}

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(response)
	}))
	defer server.Close()

	// Create client with test server URL
	client := &Client{
		httpClient: &http.Client{},
		baseURL:    server.URL,
	}

	// Test update check with CDK
	params := UpdateCheckParams{
		ResourceID:     "AUTO_MAA",
		CurrentVersion: "4.4.0.0",
		Channel:        "stable",
		CDK:            "test_cdk_123",
		UserAgent:      "TestAgent/1.0",
	}

	response, err := client.CheckUpdate(params)
	if err != nil {
		t.Fatalf("CheckUpdate with CDK failed: %v", err)
	}

	if response.Data.URL == "" {
		t.Error("Expected CDK download URL, but got empty")
	}
	if response.Data.SHA256 == "" {
		t.Error("Expected SHA256 hash, but got empty")
	}
	if response.Data.FileSize == 0 {
		t.Error("Expected file size, but got 0")
	}
}

func TestIsUpdateAvailable(t *testing.T) {
	client := NewClient()

	tests := []struct {
		name           string
		response       *MirrorResponse
		currentVersion string
		expected       bool
	}{
		{
			name: "Update available - stable",
			response: &MirrorResponse{
				Code: 0,
				Data: struct {
					VersionName     string `json:"version_name"`
					VersionNumber   int    `json:"version_number"`
					URL             string `json:"url,omitempty"`
					SHA256          string `json:"sha256,omitempty"`
					Channel         string `json:"channel"`
					OS              string `json:"os"`
					Arch            string `json:"arch"`
					UpdateType      string `json:"update_type,omitempty"`
					ReleaseNote     string `json:"release_note"`
					FileSize        int64  `json:"filesize,omitempty"`
					CDKExpiredTime  int64  `json:"cdk_expired_time,omitempty"`
				}{VersionName: "v4.4.1"},
			},
			currentVersion: "4.4.0.0",
			expected:       true,
		},
		{
			name: "No update available - same version",
			response: &MirrorResponse{
				Code: 0,
				Data: struct {
					VersionName     string `json:"version_name"`
					VersionNumber   int    `json:"version_number"`
					URL             string `json:"url,omitempty"`
					SHA256          string `json:"sha256,omitempty"`
					Channel         string `json:"channel"`
					OS              string `json:"os"`
					Arch            string `json:"arch"`
					UpdateType      string `json:"update_type,omitempty"`
					ReleaseNote     string `json:"release_note"`
					FileSize        int64  `json:"filesize,omitempty"`
					CDKExpiredTime  int64  `json:"cdk_expired_time,omitempty"`
				}{VersionName: "v4.4.0"},
			},
			currentVersion: "4.4.0.0",
			expected:       false,
		},
		{
			name: "API error",
			response: &MirrorResponse{
				Code: 1,
				Data: struct {
					VersionName     string `json:"version_name"`
					VersionNumber   int    `json:"version_number"`
					URL             string `json:"url,omitempty"`
					SHA256          string `json:"sha256,omitempty"`
					Channel         string `json:"channel"`
					OS              string `json:"os"`
					Arch            string `json:"arch"`
					UpdateType      string `json:"update_type,omitempty"`
					ReleaseNote     string `json:"release_note"`
					FileSize        int64  `json:"filesize,omitempty"`
					CDKExpiredTime  int64  `json:"cdk_expired_time,omitempty"`
				}{VersionName: "v4.4.1"},
			},
			currentVersion: "4.4.0.0",
			expected:       false,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			result := client.IsUpdateAvailable(test.response, test.currentVersion)
			if result != test.expected {
				t.Errorf("Expected %t, got %t", test.expected, result)
			}
		})
	}
}

func TestHasCDKDownloadURL(t *testing.T) {
	client := NewClient()

	tests := []struct {
		name     string
		response *MirrorResponse
		expected bool
	}{
		{
			name: "Has CDK URL",
			response: &MirrorResponse{
				Data: struct {
					VersionName     string `json:"version_name"`
					VersionNumber   int    `json:"version_number"`
					URL             string `json:"url,omitempty"`
					SHA256          string `json:"sha256,omitempty"`
					Channel         string `json:"channel"`
					OS              string `json:"os"`
					Arch            string `json:"arch"`
					UpdateType      string `json:"update_type,omitempty"`
					ReleaseNote     string `json:"release_note"`
					FileSize        int64  `json:"filesize,omitempty"`
					CDKExpiredTime  int64  `json:"cdk_expired_time,omitempty"`
				}{URL: "https://mirrorchyan.com/download/test"},
			},
			expected: true,
		},
		{
			name: "No CDK URL",
			response: &MirrorResponse{
				Data: struct {
					VersionName     string `json:"version_name"`
					VersionNumber   int    `json:"version_number"`
					URL             string `json:"url,omitempty"`
					SHA256          string `json:"sha256,omitempty"`
					Channel         string `json:"channel"`
					OS              string `json:"os"`
					Arch            string `json:"arch"`
					UpdateType      string `json:"update_type,omitempty"`
					ReleaseNote     string `json:"release_note"`
					FileSize        int64  `json:"filesize,omitempty"`
					CDKExpiredTime  int64  `json:"cdk_expired_time,omitempty"`
				}{URL: ""},
			},
			expected: false,
		},
		{
			name:     "Nil response",
			response: nil,
			expected: false,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			result := client.HasCDKDownloadURL(test.response)
			if result != test.expected {
				t.Errorf("Expected %t, got %t", test.expected, result)
			}
		})
	}
}

func TestGetDownloadURL(t *testing.T) {
	client := NewClient()

	tests := []struct {
		name     string
		response *MirrorResponse
		expected string
	}{
		{
			name: "CDK URL available",
			response: &MirrorResponse{
				Data: struct {
					VersionName     string `json:"version_name"`
					VersionNumber   int    `json:"version_number"`
					URL             string `json:"url,omitempty"`
					SHA256          string `json:"sha256,omitempty"`
					Channel         string `json:"channel"`
					OS              string `json:"os"`
					Arch            string `json:"arch"`
					UpdateType      string `json:"update_type,omitempty"`
					ReleaseNote     string `json:"release_note"`
					FileSize        int64  `json:"filesize,omitempty"`
					CDKExpiredTime  int64  `json:"cdk_expired_time,omitempty"`
				}{
					VersionName: "v4.4.1",
					URL:         "https://mirrorchyan.com/download/test",
				},
			},
			expected: "https://mirrorchyan.com/download/test",
		},
		{
			name: "Official URL fallback",
			response: &MirrorResponse{
				Data: struct {
					VersionName     string `json:"version_name"`
					VersionNumber   int    `json:"version_number"`
					URL             string `json:"url,omitempty"`
					SHA256          string `json:"sha256,omitempty"`
					Channel         string `json:"channel"`
					OS              string `json:"os"`
					Arch            string `json:"arch"`
					UpdateType      string `json:"update_type,omitempty"`
					ReleaseNote     string `json:"release_note"`
					FileSize        int64  `json:"filesize,omitempty"`
					CDKExpiredTime  int64  `json:"cdk_expired_time,omitempty"`
				}{
					VersionName: "v4.4.1",
					URL:         "",
				},
			},
			expected: "http://221.236.27.82:10197/d/AUTO_MAA/AUTO_MAA_v4.4.1.zip",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			result := client.GetDownloadURL(test.response)
			if result != test.expected {
				t.Errorf("Expected %s, got %s", test.expected, result)
			}
		})
	}
}