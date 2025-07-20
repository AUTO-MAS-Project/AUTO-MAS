package errors

import (
	"fmt"
	"time"
)

// ErrorType 定义错误类型枚举
type ErrorType int

const (
	NetworkError ErrorType = iota
	APIError
	FileError
	ConfigError
	InstallError
)

// String 返回错误类型的字符串表示
func (et ErrorType) String() string {
	switch et {
	case NetworkError:
		return "NetworkError"
	case APIError:
		return "APIError"
	case FileError:
		return "FileError"
	case ConfigError:
		return "ConfigError"
	case InstallError:
		return "InstallError"
	default:
		return "UnknownError"
	}
}

// UpdaterError 统一的错误结构体
type UpdaterError struct {
	Type      ErrorType
	Message   string
	Cause     error
	Timestamp time.Time
	Context   map[string]interface{}
}

// Error 实现error接口
func (ue *UpdaterError) Error() string {
	if ue.Cause != nil {
		return fmt.Sprintf("[%s] %s: %v", ue.Type, ue.Message, ue.Cause)
	}
	return fmt.Sprintf("[%s] %s", ue.Type, ue.Message)
}

// Unwrap 支持错误链
func (ue *UpdaterError) Unwrap() error {
	return ue.Cause
}

// NewUpdaterError 创建新的UpdaterError
func NewUpdaterError(errorType ErrorType, message string, cause error) *UpdaterError {
	return &UpdaterError{
		Type:      errorType,
		Message:   message,
		Cause:     cause,
		Timestamp: time.Now(),
		Context:   make(map[string]interface{}),
	}
}

// WithContext 添加上下文信息
func (ue *UpdaterError) WithContext(key string, value interface{}) *UpdaterError {
	ue.Context[key] = value
	return ue
}

// GetUserFriendlyMessage 获取用户友好的错误消息
func (ue *UpdaterError) GetUserFriendlyMessage() string {
	switch ue.Type {
	case NetworkError:
		return "网络连接失败，请检查网络连接后重试"
	case APIError:
		return "服务器响应异常，请稍后重试或联系技术支持"
	case FileError:
		return "文件操作失败，请检查文件权限和磁盘空间"
	case ConfigError:
		return "配置文件错误，程序将使用默认配置"
	case InstallError:
		return "安装过程中出现错误，程序将尝试回滚更改"
	default:
		return "发生未知错误，请联系技术支持"
	}
}

// RetryConfig 重试配置
type RetryConfig struct {
	MaxRetries      int
	InitialDelay    time.Duration
	MaxDelay        time.Duration
	BackoffFactor   float64
	RetryableErrors []ErrorType
}

// DefaultRetryConfig 默认重试配置
func DefaultRetryConfig() *RetryConfig {
	return &RetryConfig{
		MaxRetries:      3,
		InitialDelay:    time.Second,
		MaxDelay:        30 * time.Second,
		BackoffFactor:   2.0,
		RetryableErrors: []ErrorType{NetworkError, APIError},
	}
}

// IsRetryable 检查错误是否可重试
func (rc *RetryConfig) IsRetryable(err error) bool {
	if ue, ok := err.(*UpdaterError); ok {
		for _, retryableType := range rc.RetryableErrors {
			if ue.Type == retryableType {
				return true
			}
		}
	}
	return false
}

// CalculateDelay 计算重试延迟时间
func (rc *RetryConfig) CalculateDelay(attempt int) time.Duration {
	delay := time.Duration(float64(rc.InitialDelay) * pow(rc.BackoffFactor, float64(attempt)))
	if delay > rc.MaxDelay {
		delay = rc.MaxDelay
	}
	return delay
}

// pow 简单的幂运算实现
func pow(base, exp float64) float64 {
	result := 1.0
	for i := 0; i < int(exp); i++ {
		result *= base
	}
	return result
}

// RetryableOperation 可重试的操作函数类型
type RetryableOperation func() error

// ExecuteWithRetry 执行带重试的操作
func ExecuteWithRetry(operation RetryableOperation, config *RetryConfig) error {
	var lastErr error
	
	for attempt := 0; attempt <= config.MaxRetries; attempt++ {
		err := operation()
		if err == nil {
			return nil
		}
		
		lastErr = err
		
		// 如果不是可重试的错误，直接返回
		if !config.IsRetryable(err) {
			return err
		}
		
		// 如果已经是最后一次尝试，不再等待
		if attempt == config.MaxRetries {
			break
		}
		
		// 计算延迟时间并等待
		delay := config.CalculateDelay(attempt)
		time.Sleep(delay)
	}
	
	return lastErr
}

// ErrorHandler 错误处理器接口
type ErrorHandler interface {
	HandleError(err error) error
	ShouldRetry(err error) bool
	GetUserMessage(err error) string
}

// DefaultErrorHandler 默认错误处理器
type DefaultErrorHandler struct {
	retryConfig *RetryConfig
}

// NewDefaultErrorHandler 创建默认错误处理器
func NewDefaultErrorHandler() *DefaultErrorHandler {
	return &DefaultErrorHandler{
		retryConfig: DefaultRetryConfig(),
	}
}

// HandleError 处理错误
func (h *DefaultErrorHandler) HandleError(err error) error {
	if ue, ok := err.(*UpdaterError); ok {
		// 记录错误上下文
		ue.WithContext("handled_at", time.Now())
		return ue
	}
	
	// 将普通错误包装为UpdaterError
	return NewUpdaterError(NetworkError, "未分类错误", err)
}

// ShouldRetry 判断是否应该重试
func (h *DefaultErrorHandler) ShouldRetry(err error) bool {
	return h.retryConfig.IsRetryable(err)
}

// GetUserMessage 获取用户友好的错误消息
func (h *DefaultErrorHandler) GetUserMessage(err error) string {
	if ue, ok := err.(*UpdaterError); ok {
		return ue.GetUserFriendlyMessage()
	}
	return "发生未知错误，请联系技术支持"
}