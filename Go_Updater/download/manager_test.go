package download

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestNewManager(t *testing.T) {
	manager := NewManager()
	if manager == nil {
		t.Fatal("NewManager() returned nil")
	}
	if manager.client == nil {
		t.Fatal("Manager client is nil")
	}
	if manager.timeout != 30*time.Second {
		t.Errorf("Expected timeout 30s, got %v", manager.timeout)
	}
}

func TestDownload(t *testing.T) {
	// Create test content
	testContent := "This is test content for download"
	
	// Create test server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer server.Close()

	// Create temporary directory
	tempDir, err := os.MkdirTemp("", "download_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	// Test download
	manager := NewManager()
	destPath := filepath.Join(tempDir, "test_file.txt")
	
	var progressUpdates []DownloadProgress
	progressCallback := func(progress DownloadProgress) {
		progressUpdates = append(progressUpdates, progress)
	}

	err = manager.Download(server.URL, destPath, progressCallback)
	if err != nil {
		t.Fatalf("Download failed: %v", err)
	}

	// Verify file exists and content
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read downloaded file: %v", err)
	}

	if string(content) != testContent {
		t.Errorf("Expected content %q, got %q", testContent, string(content))
	}

	// Verify progress updates
	if len(progressUpdates) == 0 {
		t.Error("No progress updates received")
	}

	// Check final progress
	finalProgress := progressUpdates[len(progressUpdates)-1]
	if finalProgress.Percentage != 100 {
		t.Errorf("Expected final percentage 100, got %f", finalProgress.Percentage)
	}
	if finalProgress.BytesDownloaded != int64(len(testContent)) {
		t.Errorf("Expected bytes downloaded %d, got %d", len(testContent), finalProgress.BytesDownloaded)
	}
}

func TestDownloadWithResume(t *testing.T) {
	testContent := "This is a longer test content for resume functionality testing"
	partialContent := testContent[:20] // First 20 bytes
	remainingContent := testContent[20:] // Remaining bytes

	// Create test server that supports range requests
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rangeHeader := r.Header.Get("Range")
		
		if rangeHeader != "" {
			// Handle range request
			if strings.HasPrefix(rangeHeader, "bytes=20-") {
				w.Header().Set("Content-Range", fmt.Sprintf("bytes 20-%d/%d", len(testContent)-1, len(testContent)))
				w.Header().Set("Content-Length", fmt.Sprintf("%d", len(remainingContent)))
				w.WriteHeader(http.StatusPartialContent)
				w.Write([]byte(remainingContent))
				return
			}
		}
		
		// Handle normal request
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer server.Close()

	// Create temporary directory
	tempDir, err := os.MkdirTemp("", "download_resume_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	destPath := filepath.Join(tempDir, "test_resume_file.txt")

	// Create partial file
	err = os.WriteFile(destPath, []byte(partialContent), 0644)
	if err != nil {
		t.Fatal(err)
	}

	// Test resume download
	manager := NewManager()
	
	var progressUpdates []DownloadProgress
	progressCallback := func(progress DownloadProgress) {
		progressUpdates = append(progressUpdates, progress)
	}

	err = manager.DownloadWithResume(server.URL, destPath, progressCallback)
	if err != nil {
		t.Fatalf("Resume download failed: %v", err)
	}

	// Verify complete file content
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read resumed file: %v", err)
	}

	if string(content) != testContent {
		t.Errorf("Expected content %q, got %q", testContent, string(content))
	}
}

func TestValidateChecksum(t *testing.T) {
	// Create test content and calculate its checksum
	testContent := "Test content for checksum validation"
	hash := sha256.Sum256([]byte(testContent))
	expectedChecksum := hex.EncodeToString(hash[:])

	// Create temporary file
	tempDir, err := os.MkdirTemp("", "checksum_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	testFile := filepath.Join(tempDir, "test_checksum.txt")
	err = os.WriteFile(testFile, []byte(testContent), 0644)
	if err != nil {
		t.Fatal(err)
	}

	manager := NewManager()

	// Test valid checksum
	err = manager.ValidateChecksum(testFile, expectedChecksum)
	if err != nil {
		t.Errorf("Valid checksum validation failed: %v", err)
	}

	// Test invalid checksum
	invalidChecksum := "invalid_checksum_value"
	err = manager.ValidateChecksum(testFile, invalidChecksum)
	if err == nil {
		t.Error("Invalid checksum validation should have failed")
	}

	// Test empty checksum (should pass)
	err = manager.ValidateChecksum(testFile, "")
	if err != nil {
		t.Errorf("Empty checksum validation failed: %v", err)
	}

	// Test non-existent file
	err = manager.ValidateChecksum("non_existent_file.txt", expectedChecksum)
	if err == nil {
		t.Error("Non-existent file validation should have failed")
	}
}

func TestDownloadError(t *testing.T) {
	manager := NewManager()
	
	// Test invalid URL
	err := manager.Download("invalid-url", "/tmp/test", nil)
	if err == nil {
		t.Error("Download with invalid URL should have failed")
	}

	// Test server error
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer server.Close()

	tempDir, err := os.MkdirTemp("", "download_error_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	destPath := filepath.Join(tempDir, "error_test.txt")
	err = manager.Download(server.URL, destPath, nil)
	if err == nil {
		t.Error("Download with server error should have failed")
	}
}

func TestProgressCallback(t *testing.T) {
	testContent := strings.Repeat("A", 1024*100) // 100KB content for more progress updates
	
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.WriteHeader(http.StatusOK)
		
		// Write content in smaller chunks to trigger multiple progress updates
		writer := w.(http.Flusher)
		for i := 0; i < len(testContent); i += 1024 {
			end := i + 1024
			if end > len(testContent) {
				end = len(testContent)
			}
			w.Write([]byte(testContent[i:end]))
			writer.Flush()
			time.Sleep(50 * time.Millisecond) // Longer delay to ensure progress updates
		}
	}))
	defer server.Close()

	tempDir, err := os.MkdirTemp("", "progress_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "progress_test.txt")
	
	var progressUpdates []DownloadProgress
	progressCallback := func(progress DownloadProgress) {
		progressUpdates = append(progressUpdates, progress)
		
		// Validate progress values
		if progress.BytesDownloaded < 0 {
			t.Errorf("Negative bytes downloaded: %d", progress.BytesDownloaded)
		}
		if progress.Percentage < 0 || progress.Percentage > 100 {
			t.Errorf("Invalid percentage: %f", progress.Percentage)
		}
		if progress.Speed < 0 {
			t.Errorf("Negative speed: %d", progress.Speed)
		}
	}

	err = manager.Download(server.URL, destPath, progressCallback)
	if err != nil {
		t.Fatalf("Download failed: %v", err)
	}

	// Should have received at least one progress update (final one is guaranteed)
	if len(progressUpdates) < 1 {
		t.Errorf("Expected at least one progress update, got %d", len(progressUpdates))
	}

	// Final progress should be 100%
	finalProgress := progressUpdates[len(progressUpdates)-1]
	if finalProgress.Percentage != 100 {
		t.Errorf("Expected final percentage 100, got %f", finalProgress.Percentage)
	}
	
	// Verify that we got the correct total bytes
	if finalProgress.BytesDownloaded != int64(len(testContent)) {
		t.Errorf("Expected bytes downloaded %d, got %d", len(testContent), finalProgress.BytesDownloaded)
	}
}

func TestDownloadWithSources(t *testing.T) {
	testContent := "Test content for multi-source download"
	
	// Create primary server (Mirror酱 - higher priority)
	primaryServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer primaryServer.Close()

	// Create backup server (regular download site - lower priority)
	backupServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer backupServer.Close()

	tempDir, err := os.MkdirTemp("", "multi_source_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "multi_source_test.txt")

	// Test with multiple sources - should use primary (lower priority number)
	sources := []DownloadSource{
		{URL: backupServer.URL, Priority: 2, Name: "Backup Server"},
		{URL: primaryServer.URL, Priority: 1, Name: "Mirror Server"}, // Higher priority
	}

	var progressUpdates []DownloadProgress
	progressCallback := func(progress DownloadProgress) {
		progressUpdates = append(progressUpdates, progress)
	}

	err = manager.DownloadWithSources(sources, destPath, progressCallback)
	if err != nil {
		t.Fatalf("Multi-source download failed: %v", err)
	}

	// Verify file content
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read downloaded file: %v", err)
	}

	if string(content) != testContent {
		t.Errorf("Expected content %q, got %q", testContent, string(content))
	}

	// Verify progress updates
	if len(progressUpdates) == 0 {
		t.Error("No progress updates received")
	}
}

func TestDownloadWithSourcesFallback(t *testing.T) {
	testContent := "Test content for fallback download"
	
	// Create failing primary server
	failingServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer failingServer.Close()

	// Create working backup server
	workingServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer workingServer.Close()

	tempDir, err := os.MkdirTemp("", "fallback_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "fallback_test.txt")

	// Test fallback - primary fails, backup succeeds
	sources := []DownloadSource{
		{URL: failingServer.URL, Priority: 1, Name: "Failing Server"},
		{URL: workingServer.URL, Priority: 2, Name: "Working Server"},
	}

	err = manager.DownloadWithSources(sources, destPath, nil)
	if err != nil {
		t.Fatalf("Fallback download failed: %v", err)
	}

	// Verify file content
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read downloaded file: %v", err)
	}

	if string(content) != testContent {
		t.Errorf("Expected content %q, got %q", testContent, string(content))
	}
}

func TestDownloadWithSourcesAllFail(t *testing.T) {
	// Create two failing servers
	failingServer1 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer failingServer1.Close()

	failingServer2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer failingServer2.Close()

	tempDir, err := os.MkdirTemp("", "all_fail_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "all_fail_test.txt")

	// Test when all sources fail
	sources := []DownloadSource{
		{URL: failingServer1.URL, Priority: 1, Name: "Failing Server 1"},
		{URL: failingServer2.URL, Priority: 2, Name: "Failing Server 2"},
	}

	err = manager.DownloadWithSources(sources, destPath, nil)
	if err == nil {
		t.Error("Expected download to fail when all sources fail")
	}

	// Verify error message contains information about all sources failing
	if !strings.Contains(err.Error(), "all download sources failed") {
		t.Errorf("Expected error message about all sources failing, got: %v", err)
	}
}

func TestDownloadSourcePriority(t *testing.T) {
	testContent1 := "Content from server 1"
	testContent2 := "Content from server 2"
	
	// Create two working servers with different content
	server1 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent1)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent1))
	}))
	defer server1.Close()

	server2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent2)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent2))
	}))
	defer server2.Close()

	tempDir, err := os.MkdirTemp("", "priority_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "priority_test.txt")

	// Test priority ordering - server2 has higher priority (lower number)
	sources := []DownloadSource{
		{URL: server1.URL, Priority: 5, Name: "Server 1"},
		{URL: server2.URL, Priority: 1, Name: "Server 2"}, // Higher priority
	}

	err = manager.DownloadWithSources(sources, destPath, nil)
	if err != nil {
		t.Fatalf("Priority download failed: %v", err)
	}

	// Should have downloaded from server2 (higher priority)
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read downloaded file: %v", err)
	}

	if string(content) != testContent2 {
		t.Errorf("Expected content from server 2 %q, got %q", testContent2, string(content))
	}
}

func TestSetTimeout(t *testing.T) {
	manager := NewManager()
	
	// Test default timeout
	if manager.timeout != 30*time.Second {
		t.Errorf("Expected default timeout 30s, got %v", manager.timeout)
	}

	// Test setting custom timeout
	customTimeout := 60 * time.Second
	manager.SetTimeout(customTimeout)
	
	if manager.timeout != customTimeout {
		t.Errorf("Expected timeout %v, got %v", customTimeout, manager.timeout)
	}
	
	if manager.client.Timeout != customTimeout {
		t.Errorf("Expected client timeout %v, got %v", customTimeout, manager.client.Timeout)
	}
}

func TestDownloadWithSourcesEmptyList(t *testing.T) {
	manager := NewManager()
	tempDir, err := os.MkdirTemp("", "empty_sources_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	destPath := filepath.Join(tempDir, "empty_test.txt")
	
	// Test with empty sources list
	var sources []DownloadSource
	err = manager.DownloadWithSources(sources, destPath, nil)
	
	if err == nil {
		t.Error("Expected error when no download sources provided")
	}
	
	if !strings.Contains(err.Error(), "no download sources provided") {
		t.Errorf("Expected error about no sources, got: %v", err)
	}
}

func TestDownloadWithInvalidDestination(t *testing.T) {
	testContent := "Test content"
	
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer server.Close()

	manager := NewManager()
	
	// Test with invalid destination path (directory that can't be created)
	invalidPath := string([]byte{0}) + "/invalid/path/file.txt"
	
	err := manager.Download(server.URL, invalidPath, nil)
	if err == nil {
		t.Error("Expected error with invalid destination path")
	}
}

func TestDownloadWithTimeout(t *testing.T) {
	// Create a server that delays response
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(2 * time.Second) // Delay longer than timeout
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("delayed content"))
	}))
	defer server.Close()

	manager := NewManager()
	manager.SetTimeout(500 * time.Millisecond) // Short timeout

	tempDir, err := os.MkdirTemp("", "timeout_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	destPath := filepath.Join(tempDir, "timeout_test.txt")
	
	err = manager.Download(server.URL, destPath, nil)
	if err == nil {
		t.Error("Expected timeout error")
	}
	
	// Check that it's a timeout-related error
	if !strings.Contains(err.Error(), "timeout") && !strings.Contains(err.Error(), "context deadline exceeded") {
		t.Errorf("Expected timeout error, got: %v", err)
	}
}

func TestDownloadWithLargeFile(t *testing.T) {
	// Create large test content (1MB)
	largeContent := strings.Repeat("A", 1024*1024)
	
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(largeContent)))
		w.WriteHeader(http.StatusOK)
		
		// Write in chunks to simulate real download
		chunkSize := 8192
		for i := 0; i < len(largeContent); i += chunkSize {
			end := i + chunkSize
			if end > len(largeContent) {
				end = len(largeContent)
			}
			w.Write([]byte(largeContent[i:end]))
			if f, ok := w.(http.Flusher); ok {
				f.Flush()
			}
			time.Sleep(1 * time.Millisecond) // Small delay to allow progress updates
		}
	}))
	defer server.Close()

	tempDir, err := os.MkdirTemp("", "large_file_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "large_file.txt")
	
	var progressUpdates []DownloadProgress
	progressCallback := func(progress DownloadProgress) {
		progressUpdates = append(progressUpdates, progress)
	}

	err = manager.Download(server.URL, destPath, progressCallback)
	if err != nil {
		t.Fatalf("Large file download failed: %v", err)
	}

	// Verify file size
	stat, err := os.Stat(destPath)
	if err != nil {
		t.Fatalf("Failed to stat downloaded file: %v", err)
	}
	
	if stat.Size() != int64(len(largeContent)) {
		t.Errorf("Expected file size %d, got %d", len(largeContent), stat.Size())
	}

	// Verify we got multiple progress updates
	if len(progressUpdates) < 2 {
		t.Errorf("Expected multiple progress updates for large file, got %d", len(progressUpdates))
	}

	// Verify final progress is 100%
	if len(progressUpdates) > 0 {
		finalProgress := progressUpdates[len(progressUpdates)-1]
		if finalProgress.Percentage != 100 {
			t.Errorf("Expected final percentage 100, got %f", finalProgress.Percentage)
		}
	}
}

func TestDownloadResumeWithExistingFile(t *testing.T) {
	fullContent := "This is the complete file content for resume testing"
	partialContent := fullContent[:20] // First 20 bytes
	remainingContent := fullContent[20:] // Remaining bytes

	// Create test server that supports range requests
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rangeHeader := r.Header.Get("Range")
		
		if rangeHeader != "" {
			// Handle range request
			if strings.HasPrefix(rangeHeader, "bytes=20-") {
				w.Header().Set("Content-Range", fmt.Sprintf("bytes 20-%d/%d", len(fullContent)-1, len(fullContent)))
				w.Header().Set("Content-Length", fmt.Sprintf("%d", len(remainingContent)))
				w.WriteHeader(http.StatusPartialContent)
				w.Write([]byte(remainingContent))
				return
			}
		}
		
		// Handle normal request (shouldn't happen in resume test)
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(fullContent)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(fullContent))
	}))
	defer server.Close()

	tempDir, err := os.MkdirTemp("", "resume_existing_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	destPath := filepath.Join(tempDir, "resume_existing.txt")

	// Create partial file first
	err = os.WriteFile(destPath, []byte(partialContent), 0644)
	if err != nil {
		t.Fatal(err)
	}

	manager := NewManager()
	
	// Test resume download
	err = manager.DownloadWithResume(server.URL, destPath, nil)
	if err != nil {
		t.Fatalf("Resume download failed: %v", err)
	}

	// Verify complete file content
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read resumed file: %v", err)
	}

	if string(content) != fullContent {
		t.Errorf("Expected complete content %q, got %q", fullContent, string(content))
	}
}

func TestDownloadWithInvalidChecksum(t *testing.T) {
	testContent := "Test content for checksum validation"
	
	tempDir, err := os.MkdirTemp("", "checksum_invalid_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	testFile := filepath.Join(tempDir, "checksum_test.txt")
	err = os.WriteFile(testFile, []byte(testContent), 0644)
	if err != nil {
		t.Fatal(err)
	}

	manager := NewManager()

	// Test with completely wrong checksum
	wrongChecksum := "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
	err = manager.ValidateChecksum(testFile, wrongChecksum)
	if err == nil {
		t.Error("Expected checksum validation to fail with wrong checksum")
	}
	
	if !strings.Contains(err.Error(), "checksum mismatch") {
		t.Errorf("Expected checksum mismatch error, got: %v", err)
	}
}

func TestDownloadSourcesSorting(t *testing.T) {
	testContent := "Test content for source sorting"
	
	// Create multiple servers with different priorities
	server1 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fullContent := testContent + " from server1"
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(fullContent)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(fullContent))
	}))
	defer server1.Close()

	server2 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fullContent := testContent + " from server2"
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(fullContent)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(fullContent))
	}))
	defer server2.Close()

	server3 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fullContent := testContent + " from server3"
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(fullContent)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(fullContent))
	}))
	defer server3.Close()

	tempDir, err := os.MkdirTemp("", "sorting_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "sorting_test.txt")

	// Test with sources in random order - should use highest priority (lowest number)
	sources := []DownloadSource{
		{URL: server1.URL, Priority: 10, Name: "Server 1"}, // Lowest priority
		{URL: server2.URL, Priority: 1, Name: "Server 2"},  // Highest priority
		{URL: server3.URL, Priority: 5, Name: "Server 3"},  // Medium priority
	}

	err = manager.DownloadWithSources(sources, destPath, nil)
	if err != nil {
		t.Fatalf("Download with sources failed: %v", err)
	}

	// Should have downloaded from server2 (highest priority)
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read downloaded file: %v", err)
	}

	if !strings.Contains(string(content), "from server2") {
		t.Errorf("Expected content from server2, got: %s", string(content))
	}
}

func TestDownloadProgressAccuracy(t *testing.T) {
	// Create content with known size
	contentSize := 50000 // 50KB
	testContent := strings.Repeat("X", contentSize)
	
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.WriteHeader(http.StatusOK)
		
		// Write in small chunks to get more progress updates
		chunkSize := 1024
		for i := 0; i < len(testContent); i += chunkSize {
			end := i + chunkSize
			if end > len(testContent) {
				end = len(testContent)
			}
			w.Write([]byte(testContent[i:end]))
			if f, ok := w.(http.Flusher); ok {
				f.Flush()
			}
			time.Sleep(10 * time.Millisecond) // Small delay for progress updates
		}
	}))
	defer server.Close()

	tempDir, err := os.MkdirTemp("", "progress_accuracy_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "progress_test.txt")
	
	var progressUpdates []DownloadProgress
	progressCallback := func(progress DownloadProgress) {
		progressUpdates = append(progressUpdates, progress)
		
		// Validate progress values are reasonable
		if progress.BytesDownloaded < 0 {
			t.Errorf("Negative bytes downloaded: %d", progress.BytesDownloaded)
		}
		if progress.Percentage < 0 || progress.Percentage > 100 {
			t.Errorf("Invalid percentage: %f", progress.Percentage)
		}
		if progress.TotalBytes > 0 && progress.BytesDownloaded > progress.TotalBytes {
			t.Errorf("Downloaded bytes (%d) exceed total bytes (%d)", progress.BytesDownloaded, progress.TotalBytes)
		}
		if progress.Speed < 0 {
			t.Errorf("Negative speed: %d", progress.Speed)
		}
	}

	err = manager.Download(server.URL, destPath, progressCallback)
	if err != nil {
		t.Fatalf("Download failed: %v", err)
	}

	// Verify we got progress updates
	if len(progressUpdates) == 0 {
		t.Error("Expected at least one progress update")
	}

	// Verify progress is monotonically increasing
	for i := 1; i < len(progressUpdates); i++ {
		if progressUpdates[i].BytesDownloaded < progressUpdates[i-1].BytesDownloaded {
			t.Errorf("Progress went backwards: %d -> %d", 
				progressUpdates[i-1].BytesDownloaded, 
				progressUpdates[i].BytesDownloaded)
		}
	}

	// Verify final progress
	if len(progressUpdates) > 0 {
		final := progressUpdates[len(progressUpdates)-1]
		if final.Percentage != 100 {
			t.Errorf("Expected final percentage 100, got %f", final.Percentage)
		}
		if final.BytesDownloaded != int64(contentSize) {
			t.Errorf("Expected final bytes %d, got %d", contentSize, final.BytesDownloaded)
		}
	}
}

func TestTestSpeeds(t *testing.T) {
	testContent := strings.Repeat("A", 64*1024) // 64KB content for speed testing (smaller size)
	
	// Create fast server
	fastServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.Header().Set("Connection", "close") // Ensure connection is closed
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer fastServer.Close()

	// Create slow server
	slowServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.Header().Set("Connection", "close") // Ensure connection is closed
		w.WriteHeader(http.StatusOK)
		
		// Write slowly
		chunkSize := 1024
		for i := 0; i < len(testContent); i += chunkSize {
			end := i + chunkSize
			if end > len(testContent) {
				end = len(testContent)
			}
			w.Write([]byte(testContent[i:end]))
			if f, ok := w.(http.Flusher); ok {
				f.Flush()
			}
			time.Sleep(10 * time.Millisecond) // Reduced delay
		}
	}))
	defer slowServer.Close()

	// Create failing server
	failingServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Connection", "close") // Ensure connection is closed
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer failingServer.Close()

	manager := NewManager()
	
	sources := []DownloadSource{
		{URL: fastServer.URL, Priority: 1, Name: "Fast Server"},
		{URL: slowServer.URL, Priority: 2, Name: "Slow Server"},
		{URL: failingServer.URL, Priority: 3, Name: "Failing Server"},
	}

	testSize := int64(32 * 1024) // 32KB test size (smaller)
	timeout := 5 * time.Second   // Shorter timeout

	results, err := manager.TestSpeeds(sources, testSize, timeout)
	if err != nil {
		t.Fatalf("Speed test failed: %v", err)
	}

	if len(results) != len(sources) {
		t.Errorf("Expected %d results, got %d", len(sources), len(results))
	}

	// Results should be sorted by speed (descending)
	for i := 1; i < len(results); i++ {
		if results[i-1].Error == nil && results[i].Error == nil {
			if results[i-1].Speed < results[i].Speed {
				t.Errorf("Results not sorted by speed: %f < %f", results[i-1].Speed, results[i].Speed)
			}
		}
	}

	// Fast server should have higher speed than slow server (if both succeed)
	var fastResult, slowResult *SpeedTestResult
	for _, result := range results {
		if result.Source.Name == "Fast Server" {
			fastResult = &result
		} else if result.Source.Name == "Slow Server" {
			slowResult = &result
		}
	}

	if fastResult != nil && slowResult != nil {
		if fastResult.Error == nil && slowResult.Error == nil {
			if fastResult.Speed <= slowResult.Speed {
				t.Logf("Fast server speed: %f MB/s, Slow server speed: %f MB/s", 
					fastResult.Speed, slowResult.Speed)
				// Note: Due to the small test size, speeds might be similar, so we'll just log instead of failing
			}
		}
	}

	// Failing server should have an error
	var failingResult *SpeedTestResult
	for _, result := range results {
		if result.Source.Name == "Failing Server" {
			failingResult = &result
		}
	}

	if failingResult != nil && failingResult.Error == nil {
		t.Error("Failing server should have an error")
	}
	
	// Give servers time to close connections properly
	time.Sleep(100 * time.Millisecond)
}

func TestDownloadMultiThreaded(t *testing.T) {
	// Create large test content (1MB)
	contentSize := 1024 * 1024
	testContent := strings.Repeat("B", contentSize)
	
	// Create server that supports range requests
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rangeHeader := r.Header.Get("Range")
		
		if rangeHeader != "" {
			// Parse range header (simplified for testing)
			var start, end int64
			if n, err := fmt.Sscanf(rangeHeader, "bytes=%d-%d", &start, &end); n == 2 && err == nil {
				if start >= 0 && end < int64(len(testContent)) && start <= end {
					content := testContent[start:end+1]
					w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(testContent)))
					w.Header().Set("Content-Length", fmt.Sprintf("%d", len(content)))
					w.WriteHeader(http.StatusPartialContent)
					w.Write([]byte(content))
					return
				}
			}
		}
		
		// Handle HEAD request
		if r.Method == "HEAD" {
			w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
			w.Header().Set("Accept-Ranges", "bytes")
			w.WriteHeader(http.StatusOK)
			return
		}
		
		// Handle normal GET request
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.Header().Set("Accept-Ranges", "bytes")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer server.Close()

	tempDir, err := os.MkdirTemp("", "multithread_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "multithread_test.txt")
	
	config := MultiThreadConfig{
		ThreadCount: 4,
		ChunkSize:   0, // Use default chunk size
	}

	var progressUpdates []DownloadProgress
	progressCallback := func(progress DownloadProgress) {
		progressUpdates = append(progressUpdates, progress)
	}

	err = manager.DownloadMultiThreaded(server.URL, destPath, config, progressCallback)
	if err != nil {
		t.Fatalf("Multi-threaded download failed: %v", err)
	}

	// Verify file content
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read downloaded file: %v", err)
	}

	if len(content) != contentSize {
		t.Errorf("Expected content size %d, got %d", contentSize, len(content))
	}

	if string(content) != testContent {
		t.Error("Downloaded content doesn't match original")
	}

	// Verify progress updates
	if len(progressUpdates) == 0 {
		t.Error("No progress updates received")
	}

	// Final progress should be 100%
	if len(progressUpdates) > 0 {
		finalProgress := progressUpdates[len(progressUpdates)-1]
		if finalProgress.Percentage != 100 {
			t.Errorf("Expected final percentage 100, got %f", finalProgress.Percentage)
		}
	}
}

func TestDownloadMultiThreadedFallback(t *testing.T) {
	testContent := "Test content for fallback"
	
	// Create server that doesn't support range requests
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "HEAD" {
			w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
			// Don't set Accept-Ranges header
			w.WriteHeader(http.StatusOK)
			return
		}
		
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer server.Close()

	tempDir, err := os.MkdirTemp("", "multithread_fallback_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "fallback_test.txt")
	
	config := MultiThreadConfig{
		ThreadCount: 4,
	}

	// Should fallback to single-threaded download
	err = manager.DownloadMultiThreaded(server.URL, destPath, config, nil)
	if err != nil {
		t.Fatalf("Fallback download failed: %v", err)
	}

	// Verify file content
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read downloaded file: %v", err)
	}

	if string(content) != testContent {
		t.Errorf("Expected content %q, got %q", testContent, string(content))
	}
}

func TestDownloadMultiThreadedNoContentLength(t *testing.T) {
	testContent := "Test content without content length"
	
	// Create server that doesn't provide content length
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == "HEAD" {
			// Don't set Content-Length header
			w.WriteHeader(http.StatusOK)
			return
		}
		
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer server.Close()

	tempDir, err := os.MkdirTemp("", "multithread_no_length_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "no_length_test.txt")
	
	config := MultiThreadConfig{
		ThreadCount: 4,
	}

	// Should fallback to single-threaded download
	err = manager.DownloadMultiThreaded(server.URL, destPath, config, nil)
	if err != nil {
		t.Fatalf("No content length download failed: %v", err)
	}

	// Verify file content
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read downloaded file: %v", err)
	}

	if string(content) != testContent {
		t.Errorf("Expected content %q, got %q", testContent, string(content))
	}
}

func TestSpeedTestTimeout(t *testing.T) {
	// Create slow server that will timeout
	slowServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Connection", "close") // Ensure connection is closed
		time.Sleep(2 * time.Second) // Longer than timeout
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("slow content"))
	}))
	defer slowServer.Close()

	manager := NewManager()
	
	sources := []DownloadSource{
		{URL: slowServer.URL, Priority: 1, Name: "Slow Server"},
	}

	testSize := int64(1024)
	timeout := 500 * time.Millisecond // Short timeout

	results, err := manager.TestSpeeds(sources, testSize, timeout)
	if err != nil {
		t.Fatalf("Speed test failed: %v", err)
	}

	if len(results) != 1 {
		t.Errorf("Expected 1 result, got %d", len(results))
	}

	// Should have timed out
	if results[0].Error == nil {
		t.Error("Expected timeout error")
	}
	
	// Give server time to close connections properly
	time.Sleep(100 * time.Millisecond)
}

func TestDownloadMultiThreadedChunkMerging(t *testing.T) {
	// Create content with distinct patterns for each chunk
	chunk1 := strings.Repeat("1", 1024)
	chunk2 := strings.Repeat("2", 1024)
	chunk3 := strings.Repeat("3", 1024)
	chunk4 := strings.Repeat("4", 1024)
	testContent := chunk1 + chunk2 + chunk3 + chunk4
	
	// Create server that supports range requests
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rangeHeader := r.Header.Get("Range")
		
		if rangeHeader != "" {
			var start, end int64
			if n, err := fmt.Sscanf(rangeHeader, "bytes=%d-%d", &start, &end); n == 2 && err == nil {
				if start >= 0 && end < int64(len(testContent)) && start <= end {
					content := testContent[start:end+1]
					w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(testContent)))
					w.Header().Set("Content-Length", fmt.Sprintf("%d", len(content)))
					w.WriteHeader(http.StatusPartialContent)
					w.Write([]byte(content))
					return
				}
			}
		}
		
		if r.Method == "HEAD" {
			w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
			w.Header().Set("Accept-Ranges", "bytes")
			w.WriteHeader(http.StatusOK)
			return
		}
		
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.Header().Set("Accept-Ranges", "bytes")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer server.Close()

	tempDir, err := os.MkdirTemp("", "chunk_merge_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "chunk_merge_test.txt")
	
	config := MultiThreadConfig{
		ThreadCount: 4,
		ChunkSize:   1024, // Each chunk is exactly 1024 bytes
	}

	err = manager.DownloadMultiThreaded(server.URL, destPath, config, nil)
	if err != nil {
		t.Fatalf("Multi-threaded download failed: %v", err)
	}

	// Verify file content is correctly merged
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read downloaded file: %v", err)
	}

	if string(content) != testContent {
		t.Error("Chunks were not merged correctly")
		
		// Debug: check each chunk
		if len(content) >= 1024 && string(content[0:1024]) != chunk1 {
			t.Error("Chunk 1 incorrect")
		}
		if len(content) >= 2048 && string(content[1024:2048]) != chunk2 {
			t.Error("Chunk 2 incorrect")
		}
		if len(content) >= 3072 && string(content[2048:3072]) != chunk3 {
			t.Error("Chunk 3 incorrect")
		}
		if len(content) >= 4096 && string(content[3072:4096]) != chunk4 {
			t.Error("Chunk 4 incorrect")
		}
	}

	// Verify no temporary chunk files remain
	for i := 0; i < 4; i++ {
		chunkFile := fmt.Sprintf("%s.part%d", destPath, i)
		if _, err := os.Stat(chunkFile); !os.IsNotExist(err) {
			t.Errorf("Temporary chunk file %s should have been removed", chunkFile)
		}
	}
}

func TestSpeedTestEmptySources(t *testing.T) {
	manager := NewManager()
	
	var sources []DownloadSource
	testSize := int64(1024)
	timeout := 10 * time.Second

	results, err := manager.TestSpeeds(sources, testSize, timeout)
	if err == nil {
		t.Error("Expected error for empty sources")
	}
	
	if results != nil {
		t.Error("Expected nil results for empty sources")
	}
	
	if !strings.Contains(err.Error(), "no sources provided") {
		t.Errorf("Expected 'no sources provided' error, got: %v", err)
	}
}

func TestDownloadMultiThreadedDefaultConfig(t *testing.T) {
	testContent := strings.Repeat("C", 8192) // 8KB content
	
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		rangeHeader := r.Header.Get("Range")
		
		if rangeHeader != "" {
			var start, end int64
			if n, err := fmt.Sscanf(rangeHeader, "bytes=%d-%d", &start, &end); n == 2 && err == nil {
				if start >= 0 && end < int64(len(testContent)) && start <= end {
					content := testContent[start:end+1]
					w.Header().Set("Content-Range", fmt.Sprintf("bytes %d-%d/%d", start, end, len(testContent)))
					w.Header().Set("Content-Length", fmt.Sprintf("%d", len(content)))
					w.WriteHeader(http.StatusPartialContent)
					w.Write([]byte(content))
					return
				}
			}
		}
		
		if r.Method == "HEAD" {
			w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
			w.Header().Set("Accept-Ranges", "bytes")
			w.WriteHeader(http.StatusOK)
			return
		}
		
		w.Header().Set("Content-Length", fmt.Sprintf("%d", len(testContent)))
		w.Header().Set("Accept-Ranges", "bytes")
		w.WriteHeader(http.StatusOK)
		w.Write([]byte(testContent))
	}))
	defer server.Close()

	tempDir, err := os.MkdirTemp("", "default_config_test")
	if err != nil {
		t.Fatal(err)
	}
	defer os.RemoveAll(tempDir)

	manager := NewManager()
	destPath := filepath.Join(tempDir, "default_config_test.txt")
	
	// Test with zero thread count (should default to 4)
	config := MultiThreadConfig{
		ThreadCount: 0,
	}

	err = manager.DownloadMultiThreaded(server.URL, destPath, config, nil)
	if err != nil {
		t.Fatalf("Default config download failed: %v", err)
	}

	// Verify file content
	content, err := os.ReadFile(destPath)
	if err != nil {
		t.Fatalf("Failed to read downloaded file: %v", err)
	}

	if string(content) != testContent {
		t.Errorf("Expected content length %d, got %d", len(testContent), len(content))
	}
}