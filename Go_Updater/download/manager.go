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

// DownloadProgress 表示当前下载进度
type DownloadProgress struct {
	BytesDownloaded int64
	TotalBytes      int64
	Percentage      float64
	Speed           int64 // 每秒字节数
}

// ProgressCallback 在下载过程中调用以报告进度
type ProgressCallback func(DownloadProgress)

// DownloadManager 定义下载操作的接口
type DownloadManager interface {
	Download(url, destination string, progressCallback ProgressCallback) error
	DownloadWithResume(url, destination string, progressCallback ProgressCallback) error
	ValidateChecksum(filePath, expectedChecksum string) error
	SetTimeout(timeout time.Duration)
}

// Manager 实现 DownloadManager 接口
type Manager struct {
	client  *http.Client
	timeout time.Duration
}

// NewManager 创建新的下载管理器
func NewManager() *Manager {
	return &Manager{
		client: &http.Client{
			Timeout: 30 * time.Second,
		},
		timeout: 30 * time.Second,
	}
}

// Download 从给定 URL 下载文件到目标路径
func (m *Manager) Download(url, destination string, progressCallback ProgressCallback) error {
	return m.downloadWithContext(context.Background(), url, destination, progressCallback, false)
}

// DownloadWithResume 下载文件并支持断点续传
func (m *Manager) DownloadWithResume(url, destination string, progressCallback ProgressCallback) error {
	return m.downloadWithContext(context.Background(), url, destination, progressCallback, true)
}

// downloadWithContext 执行实际的下载并支持上下文
func (m *Manager) downloadWithContext(ctx context.Context, url, destination string, progressCallback ProgressCallback, resume bool) error {
	// 如果目标目录不存在则创建
	if err := os.MkdirAll(filepath.Dir(destination), 0755); err != nil {
		return fmt.Errorf("创建目标目录失败: %w", err)
	}

	// 检查文件是否存在以支持断点续传
	var existingSize int64
	if resume {
		if stat, err := os.Stat(destination); err == nil {
			existingSize = stat.Size()
		}
	}

	// 创建 HTTP 请求
	req, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return fmt.Errorf("创建请求失败: %w", err)
	}

	// 为断点续传添加范围头
	if resume && existingSize > 0 {
		req.Header.Set("Range", fmt.Sprintf("bytes=%d-", existingSize))
	}

	// 执行请求
	resp, err := m.client.Do(req)
	if err != nil {
		return fmt.Errorf("执行请求失败: %w", err)
	}
	defer resp.Body.Close()

	// 检查响应状态
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusPartialContent {
		return fmt.Errorf("意外的状态码: %d", resp.StatusCode)
	}

	// 获取总大小
	totalSize := existingSize
	if contentLength := resp.Header.Get("Content-Length"); contentLength != "" {
		if size, err := strconv.ParseInt(contentLength, 10, 64); err == nil {
			totalSize += size
		}
	}

	// 打开目标文件
	var file *os.File
	if resume && existingSize > 0 {
		file, err = os.OpenFile(destination, os.O_WRONLY|os.O_APPEND, 0644)
	} else {
		file, err = os.Create(destination)
		existingSize = 0
	}
	if err != nil {
		return fmt.Errorf("创建目标文件失败: %w", err)
	}
	defer file.Close()

	// 下载并跟踪进度
	return m.copyWithProgress(resp.Body, file, existingSize, totalSize, progressCallback)
}

// copyWithProgress 复制数据并跟踪进度
func (m *Manager) copyWithProgress(src io.Reader, dst io.Writer, startBytes, totalBytes int64, progressCallback ProgressCallback) error {
	buffer := make([]byte, 32*1024) // 32KB 缓冲区
	downloaded := startBytes
	startTime := time.Now()
	lastUpdate := startTime

	for {
		n, err := src.Read(buffer)
		if n > 0 {
			if _, writeErr := dst.Write(buffer[:n]); writeErr != nil {
				return fmt.Errorf("写入目标失败: %w", writeErr)
			}
			downloaded += int64(n)

			// 每 100ms 更新一次进度
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
			return fmt.Errorf("从源读取失败: %w", err)
		}
	}

	// 最终进度更新
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

// ValidateChecksum 验证文件的 SHA256 校验和
func (m *Manager) ValidateChecksum(filePath, expectedChecksum string) error {
	if expectedChecksum == "" {
		return nil // 没有校验和需要验证
	}

	file, err := os.Open(filePath)
	if err != nil {
		return fmt.Errorf("打开文件进行校验和验证失败: %w", err)
	}
	defer file.Close()

	hash := sha256.New()
	if _, err := io.Copy(hash, file); err != nil {
		return fmt.Errorf("计算校验和失败: %w", err)
	}

	actualChecksum := hex.EncodeToString(hash.Sum(nil))
	if actualChecksum != expectedChecksum {
		return fmt.Errorf("校验和不匹配: 期望 %s，得到 %s", expectedChecksum, actualChecksum)
	}

	return nil
}

// SetTimeout 设置下载操作的超时时间
func (m *Manager) SetTimeout(timeout time.Duration) {
	m.timeout = timeout
	m.client.Timeout = timeout
}