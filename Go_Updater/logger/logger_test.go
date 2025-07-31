package logger

import (
	"bytes"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLogLevel_String(t *testing.T) {
	tests := []struct {
		level    LogLevel
		expected string
	}{
		{DEBUG, "DEBUG"},
		{INFO, "INFO"},
		{WARN, "WARN"},
		{ERROR, "ERROR"},
		{LogLevel(999), "UNKNOWN"},
	}

	for _, tt := range tests {
		t.Run(tt.expected, func(t *testing.T) {
			if got := tt.level.String(); got != tt.expected {
				t.Errorf("LogLevel.String() = %v, want %v", got, tt.expected)
			}
		})
	}
}

func TestDefaultLoggerConfig(t *testing.T) {
	config := DefaultLoggerConfig()

	if config.Level != INFO {
		t.Errorf("Expected default level INFO, got %v", config.Level)
	}
	if config.MaxSize != 10*1024*1024 {
		t.Errorf("Expected default max size 10MB, got %v", config.MaxSize)
	}
	if config.MaxBackups != 5 {
		t.Errorf("Expected default max backups 5, got %v", config.MaxBackups)
	}
	if config.Filename != "updater.log" {
		t.Errorf("Expected default filename 'updater.log', got %v", config.Filename)
	}
}

func TestConsoleLogger(t *testing.T) {
	var buf bytes.Buffer
	logger := NewConsoleLogger(&buf)

	t.Run("log levels", func(t *testing.T) {
		logger.SetLevel(DEBUG)
		
		logger.Debug("debug message")
		logger.Info("info message")
		logger.Warn("warn message")
		logger.Error("error message")

		output := buf.String()
		if !strings.Contains(output, "DEBUG debug message") {
			t.Error("Expected debug message in output")
		}
		if !strings.Contains(output, "INFO info message") {
			t.Error("Expected info message in output")
		}
		if !strings.Contains(output, "WARN warn message") {
			t.Error("Expected warn message in output")
		}
		if !strings.Contains(output, "ERROR error message") {
			t.Error("Expected error message in output")
		}
	})

	t.Run("log level filtering", func(t *testing.T) {
		buf.Reset()
		logger.SetLevel(WARN)
		
		logger.Debug("debug message")
		logger.Info("info message")
		logger.Warn("warn message")
		logger.Error("error message")

		output := buf.String()
		if strings.Contains(output, "DEBUG") {
			t.Error("Debug message should be filtered out")
		}
		if strings.Contains(output, "INFO") {
			t.Error("Info message should be filtered out")
		}
		if !strings.Contains(output, "WARN warn message") {
			t.Error("Expected warn message in output")
		}
		if !strings.Contains(output, "ERROR error message") {
			t.Error("Expected error message in output")
		}
	})

	t.Run("formatted messages", func(t *testing.T) {
		buf.Reset()
		logger.SetLevel(DEBUG)
		
		logger.Info("formatted message: %s %d", "test", 42)
		
		output := buf.String()
		if !strings.Contains(output, "formatted message: test 42") {
			t.Error("Expected formatted message in output")
		}
	})
}

func TestFileLogger(t *testing.T) {
	// 创建临时目录
	tempDir := t.TempDir()
	
	config := &LoggerConfig{
		Level:      DEBUG,
		MaxSize:    1024, // 1KB for testing rotation
		MaxBackups: 3,
		LogDir:     tempDir,
		Filename:   "test.log",
	}

	logger, err := NewFileLogger(config)
	if err != nil {
		t.Fatalf("Failed to create file logger: %v", err)
	}
	defer logger.Close()

	t.Run("basic logging", func(t *testing.T) {
		logger.Info("test message")
		logger.Error("error message with %s", "formatting")

		// 读取日志文件
		logPath := filepath.Join(tempDir, "test.log")
		content, err := os.ReadFile(logPath)
		if err != nil {
			t.Fatalf("Failed to read log file: %v", err)
		}

		output := string(content)
		if !strings.Contains(output, "INFO test message") {
			t.Error("Expected info message in log file")
		}
		if !strings.Contains(output, "ERROR error message with formatting") {
			t.Error("Expected formatted error message in log file")
		}
	})

	t.Run("log rotation", func(t *testing.T) {
		// 写入大量数据触发轮转
		longMessage := strings.Repeat("a", 200)
		for i := 0; i < 10; i++ {
			logger.Info("Long message %d: %s", i, longMessage)
		}

		// 检查是否创建了备份文件
		logPath := filepath.Join(tempDir, "test.log")
		backupPath := filepath.Join(tempDir, "test.log.1")

		if _, err := os.Stat(logPath); os.IsNotExist(err) {
			t.Error("Main log file should exist")
		}
		if _, err := os.Stat(backupPath); os.IsNotExist(err) {
			t.Error("Backup log file should exist after rotation")
		}
	})
}

func TestMultiLogger(t *testing.T) {
	var buf1, buf2 bytes.Buffer
	logger1 := NewConsoleLogger(&buf1)
	logger2 := NewConsoleLogger(&buf2)
	
	multiLogger := NewMultiLogger(logger1, logger2)
	multiLogger.SetLevel(INFO)

	multiLogger.Info("test message")
	multiLogger.Error("error message")

	// 检查两个logger都收到了消息
	output1 := buf1.String()
	output2 := buf2.String()

	if !strings.Contains(output1, "INFO test message") {
		t.Error("Expected info message in first logger")
	}
	if !strings.Contains(output1, "ERROR error message") {
		t.Error("Expected error message in first logger")
	}
	if !strings.Contains(output2, "INFO test message") {
		t.Error("Expected info message in second logger")
	}
	if !strings.Contains(output2, "ERROR error message") {
		t.Error("Expected error message in second logger")
	}
}

func TestFileLoggerRotation(t *testing.T) {
	tempDir := t.TempDir()
	
	config := &LoggerConfig{
		Level:      DEBUG,
		MaxSize:    100, // Very small for testing
		MaxBackups: 2,
		LogDir:     tempDir,
		Filename:   "rotation_test.log",
	}

	logger, err := NewFileLogger(config)
	if err != nil {
		t.Fatalf("Failed to create file logger: %v", err)
	}
	defer logger.Close()

	// 写入足够的数据触发多次轮转
	for i := 0; i < 20; i++ {
		logger.Info("Message %d: %s", i, strings.Repeat("x", 50))
	}

	// 检查文件存在性
	logPath := filepath.Join(tempDir, "rotation_test.log")
	backup1Path := filepath.Join(tempDir, "rotation_test.log.1")
	backup2Path := filepath.Join(tempDir, "rotation_test.log.2")
	backup3Path := filepath.Join(tempDir, "rotation_test.log.3")

	if _, err := os.Stat(logPath); os.IsNotExist(err) {
		t.Error("Main log file should exist")
	}
	if _, err := os.Stat(backup1Path); os.IsNotExist(err) {
		t.Error("First backup should exist")
	}
	if _, err := os.Stat(backup2Path); os.IsNotExist(err) {
		t.Error("Second backup should exist")
	}
	// 第三个备份不应该存在（MaxBackups=2）
	if _, err := os.Stat(backup3Path); !os.IsNotExist(err) {
		t.Error("Third backup should not exist (exceeds MaxBackups)")
	}
}

func TestGlobalLoggerFunctions(t *testing.T) {
	// 这个测试比较简单，主要确保全局函数不会panic
	Debug("debug message")
	Info("info message")
	Warn("warn message")
	Error("error message")
	
	SetLevel(ERROR)
	
	// 这些调用不应该panic
	Debug("filtered debug")
	Info("filtered info")
	Error("visible error")
}

func TestFileLoggerErrorHandling(t *testing.T) {
	t.Run("invalid directory", func(t *testing.T) {
		// 使用一个真正无效的路径
		config := &LoggerConfig{
			Level:      INFO,
			MaxSize:    1024,
			MaxBackups: 3,
			LogDir:     string([]byte{0}), // 无效的路径字符
			Filename:   "test.log",
		}

		_, err := NewFileLogger(config)
		if err == nil {
			t.Error("Expected error when creating logger with invalid directory")
		}
	})
}

func TestLoggerFormatting(t *testing.T) {
	var buf bytes.Buffer
	logger := NewConsoleLogger(&buf)
	logger.SetLevel(DEBUG)

	// 测试时间戳格式
	logger.Info("test message")
	
	output := buf.String()
	lines := strings.Split(strings.TrimSpace(output), "\n")
	if len(lines) == 0 {
		t.Fatal("Expected at least one log line")
	}

	// 检查格式：[HH:MM:SS] LEVEL message
	line := lines[0]
	if !strings.Contains(line, "INFO test message") {
		t.Errorf("Expected 'INFO test message' in output, got: %s", line)
	}

	// 检查时间戳格式（简单检查）
	if !strings.HasPrefix(line, "[") {
		t.Error("Expected log line to start with timestamp in brackets")
	}
}