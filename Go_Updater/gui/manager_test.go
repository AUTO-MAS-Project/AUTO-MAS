package gui

import (
	"testing"
	"time"
)

func TestNewManager(t *testing.T) {
	manager := NewManager()
	if manager == nil {
		t.Fatal("NewManager() returned nil")
	}
	
	if manager.app == nil {
		t.Error("Manager app is nil")
	}
	
	if manager.window == nil {
		t.Error("Manager window is nil")
	}
}

func TestUpdateStatus(t *testing.T) {
	manager := NewManager()
	manager.createUIComponents()
	
	// Test different status updates
	testCases := []struct {
		status  UpdateStatus
		message string
	}{
		{StatusChecking, "检查更新中..."},
		{StatusUpdateAvailable, "发现新版本"},
		{StatusDownloading, "下载中..."},
		{StatusInstalling, "安装中..."},
		{StatusCompleted, "更新完成"},
		{StatusError, "更新失败"},
	}
	
	for _, tc := range testCases {
		manager.UpdateStatus(tc.status, tc.message)
		
		if manager.GetCurrentStatus() != tc.status {
			t.Errorf("Expected status %v, got %v", tc.status, manager.GetCurrentStatus())
		}
		
		if manager.statusLabel.Text != tc.message {
			t.Errorf("Expected message '%s', got '%s'", tc.message, manager.statusLabel.Text)
		}
	}
}

func TestShowProgress(t *testing.T) {
	manager := NewManager()
	manager.createUIComponents()
	
	// Test progress values
	testValues := []float64{0, 25.5, 50, 75.8, 100, 150, -10}
	expectedValues := []float64{0, 25.5, 50, 75.8, 100, 100, 0}
	
	for i, value := range testValues {
		manager.ShowProgress(value)
		expected := expectedValues[i] / 100.0
		
		if manager.progressBar.Value != expected {
			t.Errorf("Expected progress %.2f, got %.2f", expected, manager.progressBar.Value)
		}
	}
}

func TestSetVersionInfo(t *testing.T) {
	manager := NewManager()
	manager.createUIComponents()
	
	version := "v1.2.3"
	manager.SetVersionInfo(version)
	
	expectedText := "当前版本: v1.2.3"
	if manager.versionLabel.Text != expectedText {
		t.Errorf("Expected version text '%s', got '%s'", expectedText, manager.versionLabel.Text)
	}
}

func TestFormatSpeed(t *testing.T) {
	manager := NewManager()
	
	testCases := []struct {
		speed    int64
		expected string
	}{
		{512, "512 B/s"},
		{1536, "1.5 KB/s"},
		{1048576, "1.0 MB/s"},
		{2621440, "2.5 MB/s"},
	}
	
	for _, tc := range testCases {
		result := manager.formatSpeed(tc.speed)
		if result != tc.expected {
			t.Errorf("Expected speed format '%s', got '%s'", tc.expected, result)
		}
	}
}

func TestShowProgressWithSpeed(t *testing.T) {
	manager := NewManager()
	manager.createUIComponents()
	
	percentage := 45.5
	speed := int64(1048576) // 1 MB/s
	eta := "2分钟"
	
	manager.ShowProgressWithSpeed(percentage, speed, eta)
	
	expectedProgress := percentage / 100.0
	if manager.progressBar.Value != expectedProgress {
		t.Errorf("Expected progress %.2f, got %.2f", expectedProgress, manager.progressBar.Value)
	}
	
	expectedStatus := "下载中... 45.5% (1.0 MB/s) - 剩余时间: 2分钟"
	if manager.statusLabel.Text != expectedStatus {
		t.Errorf("Expected status '%s', got '%s'", expectedStatus, manager.statusLabel.Text)
	}
}

func TestActionButtonStates(t *testing.T) {
	manager := NewManager()
	manager.createUIComponents()
	
	// Test enabling/disabling
	manager.EnableActionButton(false)
	if !manager.actionButton.Disabled() {
		t.Error("Action button should be disabled")
	}
	
	manager.EnableActionButton(true)
	if manager.actionButton.Disabled() {
		t.Error("Action button should be enabled")
	}
	
	// Test text setting
	testText := "测试按钮"
	manager.SetActionButtonText(testText)
	if manager.actionButton.Text != testText {
		t.Errorf("Expected button text '%s', got '%s'", testText, manager.actionButton.Text)
	}
}

func TestProgressBarVisibility(t *testing.T) {
	manager := NewManager()
	manager.createUIComponents()
	
	// Initially hidden
	if manager.progressBar.Visible() {
		t.Error("Progress bar should be initially hidden")
	}
	
	// Show progress bar
	manager.ShowProgressBar()
	if !manager.progressBar.Visible() {
		t.Error("Progress bar should be visible after ShowProgressBar()")
	}
	
	// Hide progress bar
	manager.HideProgressBar()
	if manager.progressBar.Visible() {
		t.Error("Progress bar should be hidden after HideProgressBar()")
	}
}

func TestSetCallbacks(t *testing.T) {
	manager := NewManager()
	
	checkUpdateCalled := false
	cancelCalled := false
	
	onCheckUpdate := func() {
		checkUpdateCalled = true
	}
	
	onCancel := func() {
		cancelCalled = true
	}
	
	manager.SetCallbacks(onCheckUpdate, onCancel)
	
	// Verify callbacks are set
	if manager.onCheckUpdate == nil {
		t.Error("onCheckUpdate callback not set")
	}
	
	if manager.onCancel == nil {
		t.Error("onCancel callback not set")
	}
	
	// Test callback execution
	manager.onCheckUpdate()
	if !checkUpdateCalled {
		t.Error("onCheckUpdate callback was not called")
	}
	
	manager.onCancel()
	if !cancelCalled {
		t.Error("onCancel callback was not called")
	}
}

// Benchmark tests for performance
func BenchmarkUpdateStatus(b *testing.B) {
	manager := NewManager()
	manager.createUIComponents()
	
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		manager.UpdateStatus(StatusDownloading, "下载中...")
	}
}

func BenchmarkShowProgress(b *testing.B) {
	manager := NewManager()
	manager.createUIComponents()
	
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		manager.ShowProgress(float64(i % 100))
	}
}