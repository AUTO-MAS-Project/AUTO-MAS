package download

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strconv"
	"time"
)

// DownloadProgress represents the current download progress
type DownloadProgress struct {
	BytesDownloaded int64
	TotalBytes      int64
	Percentage      float64
	Speed           int64 // bytes per second
}

// ProgressCallback is called during download to report progress
type ProgressCallback func(DownloadProgress)

// DownloadManager interface defines download operations
type DownloadManager interface {
	Download(url, destination string, progressCallback ProgressCallback) error
	DownloadWithResume(url, destination string, progressCallback ProgressCallback) error
	ValidateChecksum(filePath, expectedChecksum string) error
	SetTimeout(timeout time.Duration)
}

// Manager implements DownloadManager interface
type Manager struct {
	client  *http.Client
	timeout time.Duration
}

// NewManager creates a new download manager
func NewManager() *Manager {
	return &Manager{
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
		timeout: 30 * time.Second,
	}
}

// Download downloads a file from the given URL to the destination path
func (m *Manager) Download(url, destination string, progressCallback ProgressCallback) error {
	return m.downloadWithContext(context.Background(), url, destination, progressCallback, false)
}

// DownloadWithResume downloads a file with resume capability
func (m *Manager) DownloadWithResume(url, destination string, progressCallback ProgressCallback) error {
	return m.downloadWithContext(context.Background(), url, destination, progressCallback, true)
}

// downloadWithContext performs the actual download with context support
func (m *Manager) downloadWithContext(ctx context.Context, url, destination string, progressCallback ProgressCallback, resume bool) error {
	// Create destination directory if it doesn't exist
	if err := os.MkdirAll(filepath.Dir(destination), 0755); err != nil {
		return fmt.Errorf("failed to create destination directory: %w", err)
	}

	// Check if file exists for resume
	var existingSize int64
	if resume {
		if stat, err := os.Stat(destination); err == nil {
			existingSize = stat.Size()
		}
	}

	// Create HTTP request
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	// Add range header for resume
	if resume && existingSize > 0 {
		req.Header.Set("Range", fmt.Sprintf("bytes=%d-", existingSize))
	}

	// Execute request
	resp, err := m.client.Do(req)
	if err != nil {
		return fmt.Errorf("failed to execute request: %w", err)
	}
	defer resp.Body.Close()

	// Check response status
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
		return fmt.Errorf("unexpected status code: %d", resp.StatusCode)
	}

	// Get total size
	totalSize := existingSize
	if contentLength := resp.Header.Get("Content-Length"); contentLength != "" {
		if size, err := strconv.ParseInt(contentLength, 10, 64); err == nil {
			totalSize += size
		}
	}

	// Open destination file
	var file *os.File
	if resume && existingSize > 0 {
		file, err = os.OpenFile(destination, os.O_WRONLY|os.O_APPEND, 0644)
	} else {
		file, err = os.Create(destination)
		existingSize = 0
	}
	if err != nil {
		return fmt.Errorf("failed to create destination file: %w", err)
	}
	defer file.Close()

	// Download with progress tracking
	return m.copyWithProgress(resp.Body, file, existingSize, totalSize, progressCallback)
}

// copyWithProgress copies data while tracking progress
func (m *Manager) copyWithProgress(src io.Reader, dst io.Writer, startBytes, totalBytes int64, progressCallback ProgressCallback) error {
	buffer := make([]byte, 32*1024) // 32KB buffer
	downloaded := startBytes
	startTime := time.Now()
	lastUpdate := startTime

	for {
		n, err := src.Read(buffer)
		if n > 0 {
			if _, writeErr := dst.Write(buffer[:n]); writeErr != nil {
				return fmt.Errorf("failed to write to destination: %w", writeErr)
			}
			downloaded += int64(n)

			// Update progress every 100ms
			now := time.Now()
			if progressCallback != nil && now.Sub(lastUpdate) >= 100*time.Millisecond {
				elapsed := now.Sub(startTime).Seconds()
				speed := int64(0)
				if elapsed > 0 {
					speed = int64(float64(downloaded-startBytes) / elapsed)
				}

				percentage := float64(0)
				if totalBytes > 0 {
					percentage = float64(downloaded) / float64(totalBytes) * 100
				}

				progressCallback(DownloadProgress{
					BytesDownloaded: downloaded,
					TotalBytes:      totalBytes,
					Percentage:      percentage,
					Speed:           speed,
				})
				lastUpdate = now
			}
		}

		if err == io.EOF {
			break
		}
		if err != nil {
			return fmt.Errorf("failed to read from source: %w", err)
		}
	}

	// Final progress update
	if progressCallback != nil {
		elapsed := time.Since(startTime).Seconds()
		speed := int64(0)
		if elapsed > 0 {
			speed = int64(float64(downloaded-startBytes) / elapsed)
		}

		percentage := float64(100)
		if totalBytes > 0 {
			percentage = float64(downloaded) / float64(totalBytes) * 100
		}

		progressCallback(DownloadProgress{
			BytesDownloaded: downloaded,
			TotalBytes:      totalBytes,
			Percentage:      percentage,
			Speed:           speed,
		})
	}

	return nil
}

// ValidateChecksum validates the SHA256 checksum of a file
func (m *Manager) ValidateChecksum(filePath, expectedChecksum string) error {
	if expectedChecksum == "" {
		return nil // No checksum to validate
	}

	file, err := os.Open(filePath)
	if err != nil {
		return fmt.Errorf("failed to open file for checksum validation: %w", err)
	}
	defer file.Close()

	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return fmt.Errorf("failed to calculate checksum: %w", err)
	}

	actualChecksum := hex.EncodeToString(hash.Sum(nil))
	if actualChecksum != expectedChecksum {
		return fmt.Errorf("checksum mismatch: expected %s, got %s", expectedChecksum, actualChecksum)
	}

	return nil
}

// SetTimeout sets the timeout for download operations
func (m *Manager) SetTimeout(timeout time.Duration) {
	m.timeout = timeout
	m.client.Timeout = timeout
}