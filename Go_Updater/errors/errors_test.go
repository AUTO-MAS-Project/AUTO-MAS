package errors

import (
	"fmt"
	"testing"
	"time"
)

func TestUpdaterError_Error(t *testing.T) {
	tests := []struct {
		name     string
		err      *UpdaterError
		expected string
	}{
		{
			name: "error with cause",
			err: &UpdaterError{
				Type:    NetworkError,
				Message: "connection failed",
				Cause:   fmt.Errorf("timeout"),
			},
			expected: "[NetworkError] connection failed: timeout",
		},
		{
			name: "error without cause",
			err: &UpdaterError{
				Type:    APIError,
				Message: "invalid response",
				Cause:   nil,
			},
			expected: "[APIError] invalid response",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := tt.err.Error(); got != tt.expected {
				t.Errorf("UpdaterError.Error() = %v, want %v", got, tt.expected)
			}
		})
	}
}

func TestNewUpdaterError(t *testing.T) {
	cause := fmt.Errorf("original error")
	err := NewUpdaterError(FileError, "test message", cause)

	if err.Type != FileError {
		t.Errorf("Expected type %v, got %v", FileError, err.Type)
	}
	if err.Message != "test message" {
		t.Errorf("Expected message 'test message', got '%v'", err.Message)
	}
	if err.Cause != cause {
		t.Errorf("Expected cause %v, got %v", cause, err.Cause)
	}
	if err.Context == nil {
		t.Error("Expected context to be initialized")
	}
}

func TestUpdaterError_WithContext(t *testing.T) {
	err := NewUpdaterError(ConfigError, "test", nil)
	err.WithContext("key1", "value1").WithContext("key2", 42)

	if err.Context["key1"] != "value1" {
		t.Errorf("Expected context key1 to be 'value1', got %v", err.Context["key1"])
	}
	if err.Context["key2"] != 42 {
		t.Errorf("Expected context key2 to be 42, got %v", err.Context["key2"])
	}
}

func TestUpdaterError_GetUserFriendlyMessage(t *testing.T) {
	tests := []struct {
		errorType ErrorType
		expected  string
	}{
		{NetworkError, "网络连接失败，请检查网络连接后重试"},
		{APIError, "服务器响应异常，请稍后重试或联系技术支持"},
		{FileError, "文件操作失败，请检查文件权限和磁盘空间"},
		{ConfigError, "配置文件错误，程序将使用默认配置"},
		{InstallError, "安装过程中出现错误，程序将尝试回滚更改"},
	}

	for _, tt := range tests {
		t.Run(tt.errorType.String(), func(t *testing.T) {
			err := NewUpdaterError(tt.errorType, "test", nil)
			if got := err.GetUserFriendlyMessage(); got != tt.expected {
				t.Errorf("GetUserFriendlyMessage() = %v, want %v", got, tt.expected)
			}
		})
	}
}

func TestRetryConfig_IsRetryable(t *testing.T) {
	config := DefaultRetryConfig()

	tests := []struct {
		name     string
		err      error
		expected bool
	}{
		{
			name:     "retryable network error",
			err:      NewUpdaterError(NetworkError, "test", nil),
			expected: true,
		},
		{
			name:     "retryable api error",
			err:      NewUpdaterError(APIError, "test", nil),
			expected: true,
		},
		{
			name:     "non-retryable file error",
			err:      NewUpdaterError(FileError, "test", nil),
			expected: false,
		},
		{
			name:     "regular error",
			err:      fmt.Errorf("regular error"),
			expected: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := config.IsRetryable(tt.err); got != tt.expected {
				t.Errorf("IsRetryable() = %v, want %v", got, tt.expected)
			}
		})
	}
}

func TestRetryConfig_CalculateDelay(t *testing.T) {
	config := DefaultRetryConfig()

	tests := []struct {
		attempt  int
		expected time.Duration
	}{
		{0, time.Second},
		{1, 2 * time.Second},
		{2, 4 * time.Second},
		{10, 30 * time.Second}, // should be capped at MaxDelay
	}

	for _, tt := range tests {
		t.Run(fmt.Sprintf("attempt_%d", tt.attempt), func(t *testing.T) {
			if got := config.CalculateDelay(tt.attempt); got != tt.expected {
				t.Errorf("CalculateDelay(%d) = %v, want %v", tt.attempt, got, tt.expected)
			}
		})
	}
}

func TestExecuteWithRetry(t *testing.T) {
	config := DefaultRetryConfig()
	config.InitialDelay = time.Millisecond // 加快测试速度

	t.Run("success on first try", func(t *testing.T) {
		attempts := 0
		operation := func() error {
			attempts++
			return nil
		}

		err := ExecuteWithRetry(operation, config)
		if err != nil {
			t.Errorf("Expected no error, got %v", err)
		}
		if attempts != 1 {
			t.Errorf("Expected 1 attempt, got %d", attempts)
		}
	})

	t.Run("success after retries", func(t *testing.T) {
		attempts := 0
		operation := func() error {
			attempts++
			if attempts < 3 {
				return NewUpdaterError(NetworkError, "temporary failure", nil)
			}
			return nil
		}

		err := ExecuteWithRetry(operation, config)
		if err != nil {
			t.Errorf("Expected no error, got %v", err)
		}
		if attempts != 3 {
			t.Errorf("Expected 3 attempts, got %d", attempts)
		}
	})

	t.Run("non-retryable error", func(t *testing.T) {
		attempts := 0
		operation := func() error {
			attempts++
			return NewUpdaterError(FileError, "file not found", nil)
		}

		err := ExecuteWithRetry(operation, config)
		if err == nil {
			t.Error("Expected error, got nil")
		}
		if attempts != 1 {
			t.Errorf("Expected 1 attempt, got %d", attempts)
		}
	})

	t.Run("max retries exceeded", func(t *testing.T) {
		attempts := 0
		operation := func() error {
			attempts++
			return NewUpdaterError(NetworkError, "persistent failure", nil)
		}

		err := ExecuteWithRetry(operation, config)
		if err == nil {
			t.Error("Expected error, got nil")
		}
		expectedAttempts := config.MaxRetries + 1
		if attempts != expectedAttempts {
			t.Errorf("Expected %d attempts, got %d", expectedAttempts, attempts)
		}
	})
}

func TestDefaultErrorHandler(t *testing.T) {
	handler := NewDefaultErrorHandler()

	t.Run("handle updater error", func(t *testing.T) {
		originalErr := NewUpdaterError(NetworkError, "test", nil)
		handledErr := handler.HandleError(originalErr)

		if handledErr != originalErr {
			t.Error("Expected same error instance")
		}
		if originalErr.Context["handled_at"] == nil {
			t.Error("Expected handled_at context to be set")
		}
	})

	t.Run("handle regular error", func(t *testing.T) {
		originalErr := fmt.Errorf("regular error")
		handledErr := handler.HandleError(originalErr)

		if ue, ok := handledErr.(*UpdaterError); ok {
			if ue.Type != NetworkError {
				t.Errorf("Expected NetworkError, got %v", ue.Type)
			}
			if ue.Cause != originalErr {
				t.Error("Expected original error as cause")
			}
		} else {
			t.Error("Expected UpdaterError")
		}
	})

	t.Run("should retry", func(t *testing.T) {
		retryableErr := NewUpdaterError(NetworkError, "test", nil)
		nonRetryableErr := NewUpdaterError(FileError, "test", nil)

		if !handler.ShouldRetry(retryableErr) {
			t.Error("Expected network error to be retryable")
		}
		if handler.ShouldRetry(nonRetryableErr) {
			t.Error("Expected file error to not be retryable")
		}
	})

	t.Run("get user message", func(t *testing.T) {
		updaterErr := NewUpdaterError(NetworkError, "test", nil)
		regularErr := fmt.Errorf("regular error")

		userMsg1 := handler.GetUserMessage(updaterErr)
		userMsg2 := handler.GetUserMessage(regularErr)

		if userMsg1 != "网络连接失败，请检查网络连接后重试" {
			t.Errorf("Unexpected user message: %s", userMsg1)
		}
		if userMsg2 != "发生未知错误，请联系技术支持" {
			t.Errorf("Unexpected user message: %s", userMsg2)
		}
	})
}