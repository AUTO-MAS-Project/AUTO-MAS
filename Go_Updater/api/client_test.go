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
		t.Fatal("NewClient() 返回 nil")
	}
	if client.httpClient == nil {
		t.Fatal("HTTP 客户端为 nil")
	}
	if client.baseURL != "https://mirrorchyan.com/api/resources" {
		t.Errorf("期望基础 URL 'https://mirrorchyan.com/api/resources'，得到 '%s'", client.baseURL)
	}
	if client.downloadURL != "http://221.236.27.82:10197/d/AUTO_MAA" {
		t.Errorf("期望下载 URL 'http://221.236.27.82:10197/d/AUTO_MAA'，得到 '%s'", client.downloadURL)
	}
}

func TestGetDownloadURL(t *testing.T) {
	client := NewClient()

	tests := []struct {
		versionName string
		expected    string
	}{
		{"v4.4.0", "http://221.236.27.82:10197/d/AUTO_MAA/AUTO_MAA_v4.4.0.zip"},
		{"v4.4.1-beta3", "http://221.236.27.82:10197/d/AUTO_MAA/AUTO_MAA_v4.4.1-beta.3.zip"},
		{"v1.2.3", "http://221.236.27.82:10197/d/AUTO_MAA/AUTO_MAA_v1.2.3.zip"},
	}

	for _, test := range tests {
		result := client.GetDownloadURL(test.versionName)
		if result != test.expected {
			t.Errorf("版本 %s，期望 %s，得到 %s", test.versionName, test.expected, result)
		}
	}
}

func TestCheckUpdate(t *testing.T) {
	// 创建测试服务器
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		response := MirrorResponse{
			Code: 0,
			Msg:  "success",
			Data: struct {
				VersionName   string `json:"version_name"`
				VersionNumber int    `json:"version_number"`
				URL           string `json:"url,omitempty"`
				SHA256        string `json:"sha256,omitempty"`
				Channel       string `json:"channel"`
				OS            string `json:"os"`
				Arch          string `json:"arch"`
				UpdateType    string `json:"update_type,omitempty"`
				ReleaseNote   string `json:"release_note"`
				FileSize      int64  `json:"filesize,omitempty"`
			}{
				VersionName:   "v4.4.1",
				VersionNumber: 48,
				Channel:       "stable",
				ReleaseNote:   "测试发布说明",
			},
		}

		w.Header().Set("Content-Type", "application/json")
		err := json.NewEncoder(w).Encode(response)
		if err != nil {
			return
		}
	}))
	defer server.Close()

	// 使用测试服务器 URL 创建客户端
	client := &Client{
		httpClient:  &http.Client{},
		baseURL:     server.URL,
		downloadURL: "http://221.236.27.82:10197/d/AUTO_MAA",
	}

	// 测试更新检查
	params := UpdateCheckParams{
		ResourceID:     "AUTO_MAA",
		CurrentVersion: "4.4.0.0",
		Channel:        "stable",
		UserAgent:      "TestAgent/1.0",
	}

	response, err := client.CheckUpdate(params)
	if err != nil {
		t.Fatalf("CheckUpdate 失败: %v", err)
	}

	if response.Code != 0 {
		t.Errorf("期望代码 0，得到 %d", response.Code)
	}
	if response.Data.VersionName != "v4.4.1" {
		t.Errorf("期望版本 v4.4.1，得到 %s", response.Data.VersionName)
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
			name: "有可用更新",
			response: &MirrorResponse{
				Code: 0,
				Data: struct {
					VersionName   string `json:"version_name"`
					VersionNumber int    `json:"version_number"`
					URL           string `json:"url,omitempty"`
					SHA256        string `json:"sha256,omitempty"`
					Channel       string `json:"channel"`
					OS            string `json:"os"`
					Arch          string `json:"arch"`
					UpdateType    string `json:"update_type,omitempty"`
					ReleaseNote   string `json:"release_note"`
					FileSize      int64  `json:"filesize,omitempty"`
				}{VersionName: "v4.4.1"},
			},
			currentVersion: "4.4.0.0",
			expected:       true,
		},
		{
			name: "无可用更新",
			response: &MirrorResponse{
				Code: 0,
				Data: struct {
					VersionName   string `json:"version_name"`
					VersionNumber int    `json:"version_number"`
					URL           string `json:"url,omitempty"`
					SHA256        string `json:"sha256,omitempty"`
					Channel       string `json:"channel"`
					OS            string `json:"os"`
					Arch          string `json:"arch"`
					UpdateType    string `json:"update_type,omitempty"`
					ReleaseNote   string `json:"release_note"`
					FileSize      int64  `json:"filesize,omitempty"`
				}{VersionName: "v4.4.0"},
			},
			currentVersion: "4.4.0.0",
			expected:       false,
		},
		{
			name: "beta版本有更新",
			response: &MirrorResponse{
				Code: 0,
				Data: struct {
					VersionName   string `json:"version_name"`
					VersionNumber int    `json:"version_number"`
					URL           string `json:"url,omitempty"`
					SHA256        string `json:"sha256,omitempty"`
					Channel       string `json:"channel"`
					OS            string `json:"os"`
					Arch          string `json:"arch"`
					UpdateType    string `json:"update_type,omitempty"`
					ReleaseNote   string `json:"release_note"`
					FileSize      int64  `json:"filesize,omitempty"`
				}{VersionName: "v4.4.1-beta.4"},
			},
			currentVersion: "4.4.1.3",
			expected:       true,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			result := client.IsUpdateAvailable(test.response, test.currentVersion)
			if result != test.expected {
				t.Errorf("期望 %t，得到 %t", test.expected, result)
			}
		})
	}
}
