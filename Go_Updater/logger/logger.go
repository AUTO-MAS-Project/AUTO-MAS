package logger

import (
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"sync"
	"time"
)

// LogLevel 日志级别
type LogLevel int

const (
	DEBUG LogLevel = iota
	INFO
	WARN
	ERROR
)

// String 返回日志级别的字符串表示
func (l LogLevel) String() string {
	switch l {
	case DEBUG:
		return "DEBUG"
	case INFO:
		return "INFO"
	case WARN:
		return "WARN"
	case ERROR:
		return "ERROR"
	default:
		return "UNKNOWN"
	}
}

// Logger 日志记录器接口
type Logger interface {
	Debug(msg string, fields ...interface{})
	Info(msg string, fields ...interface{})
	Warn(msg string, fields ...interface{})
	Error(msg string, fields ...interface{})
	SetLevel(level LogLevel)
	Close() error
}

// FileLogger 文件日志记录器
type FileLogger struct {
	mu          sync.RWMutex
	file        *os.File
	logger      *log.Logger
	level       LogLevel
	maxSize     int64  // 最大文件大小（字节）
	maxBackups  int    // 最大备份文件数
	logDir      string // 日志目录
	filename    string // 日志文件名
	currentSize int64  // 当前文件大小
}

// LoggerConfig 日志配置
type LoggerConfig struct {
	Level      LogLevel
	MaxSize    int64  // 最大文件大小（字节），默认10MB
	MaxBackups int    // 最大备份文件数，默认5
	LogDir     string // 日志目录，默认%APPDATA%/LightweightUpdater/logs
	Filename   string // 日志文件名，默认updater.log
}

// DefaultLoggerConfig 默认日志配置
func DefaultLoggerConfig() *LoggerConfig {
	// 获取当前可执行文件目录
	exePath, err := os.Executable()
	var logDir string
	if err != nil {
		logDir = "debug"
	} else {
		exeDir := filepath.Dir(exePath)
		logDir = filepath.Join(exeDir, "debug")
	}

	return &LoggerConfig{
		Level:      INFO,
		MaxSize:    10 * 1024 * 1024, // 10MB
		MaxBackups: 5,
		LogDir:     logDir,
		Filename:   "AUTO_MAA_Go_Updater.log",
	}
}

// NewFileLogger 创建新的文件日志记录器
func NewFileLogger(config *LoggerConfig) (*FileLogger, error) {
	if config == nil {
		config = DefaultLoggerConfig()
	}

	// 创建日志目录
	if err := os.MkdirAll(config.LogDir, 0755); err != nil {
		return nil, fmt.Errorf("failed to create log directory: %w", err)
	}

	logPath := filepath.Join(config.LogDir, config.Filename)
	
	// 打开或创建日志文件
	file, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		return nil, fmt.Errorf("failed to open log file: %w", err)
	}

	// 获取当前文件大小
	stat, err := file.Stat()
	if err != nil {
		file.Close()
		return nil, fmt.Errorf("failed to get file stats: %w", err)
	}

	logger := &FileLogger{
		file:        file,
		logger:      log.New(file, "", 0), // 我们自己处理格式
		level:       config.Level,
		maxSize:     config.MaxSize,
		maxBackups:  config.MaxBackups,
		logDir:      config.LogDir,
		filename:    config.Filename,
		currentSize: stat.Size(),
	}

	return logger, nil
}

// formatMessage 格式化日志消息
func (fl *FileLogger) formatMessage(level LogLevel, msg string, fields ...interface{}) string {
	timestamp := time.Now().Format("2006-01-02 15:04:05.000")
	
	if len(fields) > 0 {
		msg = fmt.Sprintf(msg, fields...)
	}
	
	return fmt.Sprintf("[%s] %s %s\n", timestamp, level.String(), msg)
}

// writeLog 写入日志
func (fl *FileLogger) writeLog(level LogLevel, msg string, fields ...interface{}) {
	fl.mu.Lock()
	defer fl.mu.Unlock()

	// 检查日志级别
	if level < fl.level {
		return
	}

	formattedMsg := fl.formatMessage(level, msg, fields...)
	
	// 检查是否需要轮转
	if fl.currentSize+int64(len(formattedMsg)) > fl.maxSize {
		if err := fl.rotate(); err != nil {
			// 轮转失败，尝试写入stderr
			fmt.Fprintf(os.Stderr, "Failed to rotate log: %v\n", err)
		}
	}

	// 写入日志
	n, err := fl.file.WriteString(formattedMsg)
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to write log: %v\n", err)
		return
	}
	
	fl.currentSize += int64(n)
	fl.file.Sync() // 确保写入磁盘
}

// rotate 轮转日志文件
func (fl *FileLogger) rotate() error {
	// 关闭当前文件
	if err := fl.file.Close(); err != nil {
		return fmt.Errorf("failed to close current log file: %w", err)
	}

	// 轮转备份文件
	if err := fl.rotateBackups(); err != nil {
		return fmt.Errorf("failed to rotate backups: %w", err)
	}

	// 创建新的日志文件
	logPath := filepath.Join(fl.logDir, fl.filename)
	file, err := os.OpenFile(logPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0644)
	if err != nil {
		return fmt.Errorf("failed to create new log file: %w", err)
	}

	fl.file = file
	fl.logger.SetOutput(file)
	fl.currentSize = 0

	return nil
}

// rotateBackups 轮转备份文件
func (fl *FileLogger) rotateBackups() error {
	basePath := filepath.Join(fl.logDir, fl.filename)
	
	// 删除最老的备份文件
	if fl.maxBackups > 0 {
		oldestBackup := fmt.Sprintf("%s.%d", basePath, fl.maxBackups)
		os.Remove(oldestBackup) // 忽略错误，文件可能不存在
	}

	// 重命名现有备份文件
	for i := fl.maxBackups - 1; i > 0; i-- {
		oldName := fmt.Sprintf("%s.%d", basePath, i)
		newName := fmt.Sprintf("%s.%d", basePath, i+1)
		os.Rename(oldName, newName) // 忽略错误，文件可能不存在
	}

	// 将当前日志文件重命名为第一个备份
	if fl.maxBackups > 0 {
		backupName := fmt.Sprintf("%s.1", basePath)
		return os.Rename(basePath, backupName)
	}

	return nil
}

// Debug 记录调试级别日志
func (fl *FileLogger) Debug(msg string, fields ...interface{}) {
	fl.writeLog(DEBUG, msg, fields...)
}

// Info 记录信息级别日志
func (fl *FileLogger) Info(msg string, fields ...interface{}) {
	fl.writeLog(INFO, msg, fields...)
}

// Warn 记录警告级别日志
func (fl *FileLogger) Warn(msg string, fields ...interface{}) {
	fl.writeLog(WARN, msg, fields...)
}

// Error 记录错误级别日志
func (fl *FileLogger) Error(msg string, fields ...interface{}) {
	fl.writeLog(ERROR, msg, fields...)
}

// SetLevel 设置日志级别
func (fl *FileLogger) SetLevel(level LogLevel) {
	fl.mu.Lock()
	defer fl.mu.Unlock()
	fl.level = level
}

// Close 关闭日志记录器
func (fl *FileLogger) Close() error {
	fl.mu.Lock()
	defer fl.mu.Unlock()
	
	if fl.file != nil {
		return fl.file.Close()
	}
	return nil
}

// MultiLogger 多输出日志记录器
type MultiLogger struct {
	loggers []Logger
	level   LogLevel
}

// NewMultiLogger 创建多输出日志记录器
func NewMultiLogger(loggers ...Logger) *MultiLogger {
	return &MultiLogger{
		loggers: loggers,
		level:   INFO,
	}
}

// Debug 记录调试级别日志
func (ml *MultiLogger) Debug(msg string, fields ...interface{}) {
	for _, logger := range ml.loggers {
		logger.Debug(msg, fields...)
	}
}

// Info 记录信息级别日志
func (ml *MultiLogger) Info(msg string, fields ...interface{}) {
	for _, logger := range ml.loggers {
		logger.Info(msg, fields...)
	}
}

// Warn 记录警告级别日志
func (ml *MultiLogger) Warn(msg string, fields ...interface{}) {
	for _, logger := range ml.loggers {
		logger.Warn(msg, fields...)
	}
}

// Error 记录错误级别日志
func (ml *MultiLogger) Error(msg string, fields ...interface{}) {
	for _, logger := range ml.loggers {
		logger.Error(msg, fields...)
	}
}

// SetLevel 设置日志级别
func (ml *MultiLogger) SetLevel(level LogLevel) {
	ml.level = level
	for _, logger := range ml.loggers {
		logger.SetLevel(level)
	}
}

// Close 关闭所有日志记录器
func (ml *MultiLogger) Close() error {
	var lastErr error
	for _, logger := range ml.loggers {
		if err := logger.Close(); err != nil {
			lastErr = err
		}
	}
	return lastErr
}

// ConsoleLogger 控制台日志记录器
type ConsoleLogger struct {
	writer io.Writer
	level  LogLevel
}

// NewConsoleLogger 创建控制台日志记录器
func NewConsoleLogger(writer io.Writer) *ConsoleLogger {
	if writer == nil {
		writer = os.Stdout
	}
	return &ConsoleLogger{
		writer: writer,
		level:  INFO,
	}
}

// formatMessage 格式化控制台日志消息
func (cl *ConsoleLogger) formatMessage(level LogLevel, msg string, fields ...interface{}) string {
	timestamp := time.Now().Format("15:04:05")
	
	if len(fields) > 0 {
		msg = fmt.Sprintf(msg, fields...)
	}
	
	return fmt.Sprintf("[%s] %s %s\n", timestamp, level.String(), msg)
}

// writeLog 写入控制台日志
func (cl *ConsoleLogger) writeLog(level LogLevel, msg string, fields ...interface{}) {
	if level < cl.level {
		return
	}
	
	formattedMsg := cl.formatMessage(level, msg, fields...)
	fmt.Fprint(cl.writer, formattedMsg)
}

// Debug 记录调试级别日志
func (cl *ConsoleLogger) Debug(msg string, fields ...interface{}) {
	cl.writeLog(DEBUG, msg, fields...)
}

// Info 记录信息级别日志
func (cl *ConsoleLogger) Info(msg string, fields ...interface{}) {
	cl.writeLog(INFO, msg, fields...)
}

// Warn 记录警告级别日志
func (cl *ConsoleLogger) Warn(msg string, fields ...interface{}) {
	cl.writeLog(WARN, msg, fields...)
}

// Error 记录错误级别日志
func (cl *ConsoleLogger) Error(msg string, fields ...interface{}) {
	cl.writeLog(ERROR, msg, fields...)
}

// SetLevel 设置日志级别
func (cl *ConsoleLogger) SetLevel(level LogLevel) {
	cl.level = level
}

// Close 关闭控制台日志记录器（无操作）
func (cl *ConsoleLogger) Close() error {
	return nil
}

// 全局日志记录器实例
var (
	defaultLogger Logger
	once          sync.Once
)

// GetDefaultLogger 获取默认日志记录器
func GetDefaultLogger() Logger {
	once.Do(func() {
		fileLogger, err := NewFileLogger(DefaultLoggerConfig())
		if err != nil {
			// 如果文件日志创建失败，使用控制台日志
			defaultLogger = NewConsoleLogger(os.Stderr)
		} else {
			// 同时输出到文件和控制台
			consoleLogger := NewConsoleLogger(os.Stdout)
			defaultLogger = NewMultiLogger(fileLogger, consoleLogger)
		}
	})
	return defaultLogger
}

// 便捷函数
func Debug(msg string, fields ...interface{}) {
	GetDefaultLogger().Debug(msg, fields...)
}

func Info(msg string, fields ...interface{}) {
	GetDefaultLogger().Info(msg, fields...)
}

func Warn(msg string, fields ...interface{}) {
	GetDefaultLogger().Warn(msg, fields...)
}

func Error(msg string, fields ...interface{}) {
	GetDefaultLogger().Error(msg, fields...)
}

func SetLevel(level LogLevel) {
	GetDefaultLogger().SetLevel(level)
}

func Close() error {
	return GetDefaultLogger().Close()
}