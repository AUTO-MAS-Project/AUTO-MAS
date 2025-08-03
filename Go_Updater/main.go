package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"

	"AUTO_MAA_Go_Updater/api"
	"AUTO_MAA_Go_Updater/config"
	"AUTO_MAA_Go_Updater/download"
	"AUTO_MAA_Go_Updater/errors"
	"AUTO_MAA_Go_Updater/install"
	"AUTO_MAA_Go_Updater/logger"
	appversion "AUTO_MAA_Go_Updater/version"
)

// UpdateState 表示更新过程的当前状态
type UpdateState int

const (
	StateIdle UpdateState = iota
	StateChecking
	StateUpdateAvailable
	StateDownloading
	StateInstalling
	StateCompleted
	StateError
)

// String 返回更新状态的字符串表示
func (s UpdateState) String() string {
	switch s {
	case StateIdle:
		return "Idle"
	case StateChecking:
		return "Checking"
	case StateUpdateAvailable:
		return "UpdateAvailable"
	case StateDownloading:
		return "Downloading"
	case StateInstalling:
		return "Installing"
	case StateCompleted:
		return "Completed"
	case StateError:
		return "Error"
	default:
		return "Unknown"
	}
}

// GUIManager 可选 GUI 功能的接口
type GUIManager interface {
	ShowMainWindow()
	UpdateStatus(status int, message string)
	ShowProgress(percentage float64)
	ShowError(errorMsg string)
	Close()
}

// UpdateInfo 包含可用更新的信息
type UpdateInfo struct {
	CurrentVersion string
	NewVersion     string
	DownloadURL    string
	ReleaseNotes   string
	IsAvailable    bool
}

// Application 表示主应用程序实例
type Application struct {
	config          *config.Config
	configManager   config.ConfigManager
	apiClient       api.MirrorClient
	downloadManager download.DownloadManager
	installManager  install.InstallManager
	guiManager      GUIManager
	logger          logger.Logger
	errorHandler    errors.ErrorHandler
	ctx             context.Context
	cancel          context.CancelFunc
	wg              sync.WaitGroup

	// 更新流程状态
	currentState  UpdateState
	stateMutex    sync.RWMutex
	updateInfo    *UpdateInfo
	userConfirmed chan bool
}

// 命令行标志
var (
	configPath     = flag.String("config", "", "Path to configuration file")
	logLevel       = flag.String("log-level", "info", "Log level (debug, info, warn, error)")
	noGUI          = flag.Bool("no-gui", false, "Run without GUI (command line mode)")
	version        = flag.Bool("version", false, "Show version information")
	help           = flag.Bool("help", false, "Show help information")
	channel        = flag.String("channel", "", "Update channel (stable or beta)")
	currentVersion = flag.String("current-version", "", "Current version to check against")
)

// 版本信息现在由 version 包处理

func main() {
	// 解析命令行参数
	flag.Parse()

	// 显示版本信息
	if *version {
		showVersion()
		return
	}

	// 显示帮助信息
	if *help {
		showHelp()
		return
	}

	// 检查单实例运行
	if err := ensureSingleInstance(); err != nil {
		fmt.Fprintf(os.Stderr, "另一个实例已在运行: %v\n", err)
		os.Exit(1)
	}

	// 初始化应用程序
	app, err := initializeApplication()
	if err != nil {
		fmt.Fprintf(os.Stderr, "初始化应用程序失败: %v\n", err)
		os.Exit(1)
	}
	defer app.cleanup()

	// 处理启动时标记删除的文件清理
	if err := app.handleStartupCleanup(); err != nil {
		app.logger.Warn("清理标记文件失败: %v", err)
	}

	// 设置信号处理
	app.setupSignalHandling()

	// 启动应用程序
	if err := app.run(); err != nil {
		app.logger.Error("应用程序错误: %v", err)
		os.Exit(1)
	}
}

// initializeApplication 初始化所有应用程序组件
func initializeApplication() (*Application, error) {
	// 创建优雅关闭的上下文
	ctx, cancel := context.WithCancel(context.Background())

	// 首先初始化日志记录器
	loggerConfig := logger.DefaultLoggerConfig()

	// 从命令行设置日志级别
	switch *logLevel {
	case "debug":
		loggerConfig.Level = logger.DEBUG
	case "info":
		loggerConfig.Level = logger.INFO
	case "warn":
		loggerConfig.Level = logger.WARN
	case "error":
		loggerConfig.Level = logger.ERROR
	}

	var appLogger logger.Logger
	fileLogger, err := logger.NewFileLogger(loggerConfig)
	if err != nil {
		// 回退到控制台日志记录器
		appLogger = logger.NewConsoleLogger(os.Stdout)
	} else {
		appLogger = fileLogger
	}

	appLogger.Info("正在初始化 AUTO_MAA_Go_Updater v%s", appversion.Version)

	// 初始化配置管理器
	var configManager config.ConfigManager
	if *configPath != "" {
		// 自定义配置路径尚未在配置包中实现
		// 目前使用默认管理器
		configManager = config.NewConfigManager()
		appLogger.Warn("自定义配置路径尚未完全支持，使用默认配置")
	} else {
		configManager = config.NewConfigManager()
	}

	// 加载配置
	cfg, err := configManager.Load()
	if err != nil {
		appLogger.Error("加载配置失败: %v", err)
		return nil, fmt.Errorf("加载配置失败: %w", err)
	}

	appLogger.Info("配置加载成功")

	// 初始化 API 客户端
	apiClient := api.NewClient()

	// 初始化下载管理器
	downloadManager := download.NewManager()

	// 初始化安装管理器
	installManager := install.NewManager()

	// 初始化错误处理器
	errorHandler := errors.NewDefaultErrorHandler()

	// 初始化 GUI 管理器（如果不是无 GUI 模式）
	var guiManager GUIManager
	if !*noGUI {
		// GUI 将在 GUI 依赖项可用时实现
		appLogger.Info("请求 GUI 模式但此构建中不可用")
		guiManager = nil
	} else {
		appLogger.Info("运行在无 GUI 模式")
	}

	app := &Application{
		config:          cfg,
		configManager:   configManager,
		apiClient:       apiClient,
		downloadManager: downloadManager,
		installManager:  installManager,
		guiManager:      guiManager,
		logger:          appLogger,
		errorHandler:    errorHandler,
		ctx:             ctx,
		cancel:          cancel,
		currentState:    StateIdle,
		userConfirmed:   make(chan bool, 1),
	}

	appLogger.Info("应用程序初始化成功")
	return app, nil
}

// run 启动主应用程序逻辑
func (app *Application) run() error {
	app.logger.Info("启动应用程序")

	if app.guiManager != nil {
		// 使用 GUI 运行
		return app.runWithGUI()
	} else {
		// 在命令行模式下运行
		return app.runCommandLine()
	}
}

// runWithGUI 使用 GUI 运行应用程序
func (app *Application) runWithGUI() error {
	app.logger.Info("启动 GUI 模式")

	// 设置 GUI 回调
	app.setupGUICallbacks()

	// 显示主窗口（这将阻塞直到窗口关闭）
	app.guiManager.ShowMainWindow()

	return nil
}

// runCommandLine 在命令行模式下运行应用程序
func (app *Application) runCommandLine() error {
	app.logger.Info("启动命令行模式")

	// 开始完整的更新流程
	return app.executeUpdateFlow()
}

// setupGUICallbacks 为 GUI 交互设置回调
func (app *Application) setupGUICallbacks() {
	if app.guiManager == nil {
		return
	}

	// GUI 回调将在 GUI 可用时实现
	app.logger.Info("请求 GUI 回调设置但 GUI 不可用")

	// 目前，我们将设置基本的交互处理
	// 实际的 GUI 集成将在 GUI 依赖项解决后完成
}

// handleStartupCleanup 处理启动时标记删除的文件清理
func (app *Application) handleStartupCleanup() error {
	app.logger.Info("执行启动清理")

	// 获取当前可执行文件目录
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("获取可执行文件路径失败: %w", err)
	}

	exeDir := filepath.Dir(exePath)

	// 删除标记删除的文件
	if installMgr, ok := app.installManager.(*install.Manager); ok {
		if err := installMgr.DeleteMarkedFiles(exeDir); err != nil {
			return fmt.Errorf("删除标记文件失败: %w", err)
		}
	}

	app.logger.Info("启动清理完成")
	return nil
}

// setupSignalHandling 设置系统信号的优雅关闭
func (app *Application) setupSignalHandling() {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)

	go func() {
		sig := <-sigChan
		app.logger.Info("接收到信号: %v", sig)
		app.logger.Info("启动优雅关闭...")
		app.cancel()
	}()
}

// cleanup 执行应用程序清理
func (app *Application) cleanup() {
	app.logger.Info("清理应用程序资源")

	// 取消上下文以停止所有操作
	app.cancel()

	// 等待所有 goroutine 完成
	app.wg.Wait()

	// 清理安装管理器临时目录
	if installMgr, ok := app.installManager.(*install.Manager); ok {
		if err := installMgr.CleanupAllTempDirs(); err != nil {
			app.logger.Error("清理临时目录失败: %v", err)
		}
	}

	app.logger.Info("应用程序清理完成")

	// 最后关闭日志记录器
	if err := app.logger.Close(); err != nil {
		fmt.Fprintf(os.Stderr, "关闭日志记录器失败: %v\n", err)
	}
}

// ensureSingleInstance 确保应用程序只有一个实例在运行
func ensureSingleInstance() error {
	// 在临时目录中创建锁文件
	tempDir := os.TempDir()
	lockFile := filepath.Join(tempDir, "AUTO_MAA_Go_Updater.lock")

	// 尝试独占创建锁文件
	file, err := os.OpenFile(lockFile, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0644)
	if err != nil {
		if os.IsExist(err) {
			// 检查进程是否仍在运行
			if isProcessRunning(lockFile) {
				return fmt.Errorf("另一个实例已在运行")
			}
			// 删除过期的锁文件并重试
			os.Remove(lockFile)
			return ensureSingleInstance()
		}
		return fmt.Errorf("创建锁文件失败: %w", err)
	}

	// 将当前进程 ID 写入锁文件
	fmt.Fprintf(file, "%d", os.Getpid())
	file.Close()

	// 退出时删除锁文件
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
		<-sigChan
		os.Remove(lockFile)
	}()

	return nil
}

// isProcessRunning 检查锁文件中的进程是否仍在运行
func isProcessRunning(lockFile string) bool {
	data, err := os.ReadFile(lockFile)
	if err != nil {
		return false
	}

	var pid int
	if _, err := fmt.Sscanf(string(data), "%d", &pid); err != nil {
		return false
	}

	// 检查进程是否存在（Windows 特定）
	process, err := os.FindProcess(pid)
	if err != nil {
		return false
	}

	// 在 Windows 上，FindProcess 总是成功，所以我们需要不同的检查方式
	// 尝试发送信号 0 来检查进程是否存在
	err = process.Signal(syscall.Signal(0))
	return err == nil
}

// showVersion 显示版本信息
func showVersion() {
	fmt.Printf("AUTO_MAA_Go_Updater\n")
	fmt.Printf("Version: %s\n", appversion.Version)
	fmt.Printf("Build Time: %s\n", appversion.BuildTime)
	fmt.Printf("Git Commit: %s\n", appversion.GitCommit)
}

// showHelp 显示帮助信息
func showHelp() {
	fmt.Printf("AUTO_MAA_Go_Updater\n\n")
	fmt.Printf("Usage: %s [options]\n\n", os.Args[0])
	fmt.Printf("Options:\n")
	flag.PrintDefaults()
	fmt.Printf("\nExamples:\n")
	fmt.Printf("  %s                    # 使用 GUI 运行\n", os.Args[0])
	fmt.Printf("  %s -no-gui           # 在命令行模式下运行\n", os.Args[0])
	fmt.Printf("  %s -log-level debug  # 使用调试日志运行\n", os.Args[0])
	fmt.Printf("  %s -version          # 显示版本信息\n", os.Args[0])
}

// executeUpdateFlow 执行完整的更新流程和状态机管理
func (app *Application) executeUpdateFlow() error {
	app.logger.Info("开始执行更新流程")

	// 执行状态机
	for {
		select {
		case <-app.ctx.Done():
			app.logger.Info("更新流程已取消")
			return app.ctx.Err()
		default:
		}

		// 获取当前状态
		state := app.getCurrentState()
		app.logger.Debug("当前状态: %s", state.String())

		// 执行状态逻辑
		nextState, err := app.executeState(state)
		if err != nil {
			app.logger.Error("状态执行失败: %v", err)
			app.setState(StateError)
			return err
		}

		// 检查是否完成
		if nextState == StateCompleted || nextState == StateError {
			app.setState(nextState)
			break
		}

		// 转换到下一个状态
		app.setState(nextState)
	}

	finalState := app.getCurrentState()
	app.logger.Info("更新流程完成，状态: %s", finalState.String())

	if finalState == StateError {
		return fmt.Errorf("更新流程失败")
	}

	return nil
}

// executeState 执行当前状态的逻辑并返回下一个状态
func (app *Application) executeState(state UpdateState) (UpdateState, error) {
	switch state {
	case StateIdle:
		return app.executeIdleState()
	case StateChecking:
		return app.executeCheckingState()
	case StateUpdateAvailable:
		return app.executeUpdateAvailableState()
	case StateDownloading:
		return app.executeDownloadingState()
	case StateInstalling:
		return app.executeInstallingState()
	case StateCompleted:
		return StateCompleted, nil
	case StateError:
		return StateError, nil
	default:
		return StateError, fmt.Errorf("未知状态: %s", state.String())
	}
}

// executeIdleState 处理空闲状态
func (app *Application) executeIdleState() (UpdateState, error) {
	app.logger.Info("开始更新检查...")
	fmt.Println("正在检查更新...")
	return StateChecking, nil
}

// executeCheckingState 处理检查状态
func (app *Application) executeCheckingState() (UpdateState, error) {
	app.logger.Info("检查更新中")

	// 确定要使用的版本和渠道
	var currentVer, updateChannel string
	var err error

	// 优先级: 命令行参数 > 版本文件 > 配置
	if *currentVersion != "" {
		currentVer = *currentVersion
		app.logger.Info("使用命令行当前版本: %s", currentVer)
	} else {
		// 尝试从 resources/version.json 加载版本
		versionManager := appversion.NewVersionManager()
		versionInfo, err := versionManager.LoadVersionFromFile()
		if err != nil {
			app.logger.Warn("从文件加载版本失败: %v，使用配置版本", err)
			currentVer = app.config.CurrentVersion
		} else {
			currentVer = versionInfo.MainVersion
			app.logger.Info("使用版本文件中的当前版本: %s", currentVer)
		}
	}

	// 确定渠道
	if *channel != "" {
		updateChannel = *channel
		app.logger.Info("使用命令行渠道: %s", updateChannel)
	} else {
		// 尝试从 config.json 加载渠道
		updateChannel = app.loadChannelFromConfig()
		app.logger.Info("使用配置中的渠道: %s", updateChannel)
	}

	// 准备 API 参数
	params := api.UpdateCheckParams{
		ResourceID:     "AUTO_MAA", // AUTO_MAA 的固定资源 ID
		CurrentVersion: currentVer,
		Channel:        updateChannel,
		UserAgent:      app.config.UserAgent,
	}

	// 调用 MirrorChyan API 检查更新
	response, err := app.apiClient.CheckUpdate(params)
	switch updateChannel {
	case "beta":
		fmt.Println("检查更新类别：公测版")
	case "stable":
		fmt.Println("检查更新类别：稳定版")
	default:
		fmt.Printf("检查更新类别：%v\n", updateChannel)
	}
	fmt.Printf("当前版本：%s\n", app.formatVersionForDisplay(currentVer))
	app.logger.Info("当前更新类别：" + updateChannel + "；当前版本：" + currentVer)
	if err != nil {
		app.logger.Error("检查更新失败: %v", err)
		fmt.Printf("检查更新失败: %v\n", err)
		return StateError, fmt.Errorf("检查更新失败: %w", err)
	}

	// 检查是否有可用更新
	isUpdateAvailable := app.apiClient.IsUpdateAvailable(response, currentVer)

	if !isUpdateAvailable {
		app.logger.Info("无可用更新")
		fmt.Println("当前已是最新版本")

		// 延迟 5 秒再退出
		fmt.Println("5 秒后自动退出...")
		time.Sleep(5 * time.Second)

		return StateCompleted, nil
	}

	// 使用下载站获取下载链接
	downloadURL := app.apiClient.GetDownloadURL(response.Data.VersionName)
	app.logger.Info("使用下载站 URL: %s", downloadURL)

	// 存储更新信息
	app.updateInfo = &UpdateInfo{
		CurrentVersion: currentVer,
		NewVersion:     response.Data.VersionName,
		DownloadURL:    downloadURL,
		ReleaseNotes:   response.Data.ReleaseNote,
		IsAvailable:    true,
	}

	app.logger.Info("有可用更新: %s -> %s", currentVer, response.Data.VersionName)
	fmt.Printf("发现新版本: %s -> %s\n", app.formatVersionForDisplay(currentVer), response.Data.VersionName)

	return StateUpdateAvailable, nil
}

// executeUpdateAvailableState 处理更新可用状态
func (app *Application) executeUpdateAvailableState() (UpdateState, error) {
	app.logger.Info("有可用更新，自动开始下载")

	// 自动开始下载，无需用户确认
	fmt.Println("开始下载更新...")
	return StateDownloading, nil
}

// executeDownloadingState 处理下载状态
func (app *Application) executeDownloadingState() (UpdateState, error) {
	app.logger.Info("开始下载")

	if app.updateInfo == nil || app.updateInfo.DownloadURL == "" {
		return StateError, fmt.Errorf("无可用下载 URL")
	}

	// 获取当前可执行文件目录
	exePath, err := os.Executable()
	if err != nil {
		return StateError, fmt.Errorf("获取可执行文件路径失败: %w", err)
	}
	exeDir := filepath.Dir(exePath)

	// 为下载创建 AUTOMAA_UPDATE_TEMP 目录
	tempDir := filepath.Join(exeDir, "AUTOMAA_UPDATE_TEMP")
	if err := os.MkdirAll(tempDir, 0755); err != nil {
		return StateError, fmt.Errorf("创建临时目录失败: %w", err)
	}

	// 下载文件
	downloadPath := filepath.Join(tempDir, "update.zip")

	fmt.Println("正在下载更新包...")

	// 创建进度回调
	progressCallback := func(progress download.DownloadProgress) {
		if progress.TotalBytes > 0 {
			fmt.Printf("\r下载进度: %.1f%% (%s/s)",
				progress.Percentage,
				app.formatBytes(progress.Speed))
		}
	}

	// 下载更新文件
	downloadErr := app.downloadManager.Download(app.updateInfo.DownloadURL, downloadPath, progressCallback)

	fmt.Println() // 进度后换行

	if downloadErr != nil {
		app.logger.Error("下载失败: %v", downloadErr)
		fmt.Printf("下载失败: %v\n", downloadErr)
		return StateError, fmt.Errorf("下载失败: %w", downloadErr)
	}

	app.logger.Info("下载成功完成")
	fmt.Println("下载完成")

	// 存储下载路径用于安装
	app.updateInfo.DownloadURL = downloadPath

	return StateInstalling, nil
}

// executeInstallingState 处理安装状态
func (app *Application) executeInstallingState() (UpdateState, error) {
	app.logger.Info("开始安装")
	fmt.Println("正在安装更新...")

	if app.updateInfo == nil || app.updateInfo.DownloadURL == "" {
		return StateError, fmt.Errorf("无可用下载文件")
	}

	downloadPath := app.updateInfo.DownloadURL

	// 为解压创建临时目录
	tempDir, err := app.installManager.CreateTempDir()
	if err != nil {
		return StateError, fmt.Errorf("创建临时目录失败: %w", err)
	}

	// 解压下载的 zip 文件
	app.logger.Info("解压更新包")
	if err := app.installManager.ExtractZip(downloadPath, tempDir); err != nil {
		app.logger.Error("解压 zip 失败: %v", err)
		return StateError, fmt.Errorf("解压更新包失败: %w", err)
	}

	// 如果存在 changes.json 则处理（供将来使用）
	changesPath := filepath.Join(tempDir, "changes.json")
	_, err = app.installManager.ProcessChanges(changesPath)
	if err != nil {
		app.logger.Warn("处理变更失败（非关键）: %v", err)
		// 这对于 AUTO_MAA-Setup.exe 安装不是关键的
	}

	// 获取当前可执行文件目录
	exePath, err := os.Executable()
	if err != nil {
		return StateError, fmt.Errorf("获取可执行文件路径失败: %w", err)
	}
	targetDir := filepath.Dir(exePath)

	// 处理正在运行的进程（但跳过更新器本身）
	updaterName := filepath.Base(exePath)
	if err := app.handleRunningProcesses(targetDir, updaterName); err != nil {
		app.logger.Warn("处理正在运行的进程失败: %v", err)
		// 继续安装，这不是关键的
	}

	// 在解压的文件中查找 AUTO_MAA-Setup.exe
	setupExePath := filepath.Join(tempDir, "AUTO_MAA-Setup.exe")
	if _, err := os.Stat(setupExePath); err != nil {
		app.logger.Error("在更新包中未找到 AUTO_MAA-Setup.exe: %v", err)
		return StateError, fmt.Errorf("在更新包中未找到 AUTO_MAA-Setup.exe: %w", err)
	}

	// 运行安装可执行文件
	app.logger.Info("运行 AUTO_MAA-Setup.exe")
	fmt.Println("正在运行安装程序...")

	if err := app.runSetupExecutable(setupExePath); err != nil {
		app.logger.Error("运行安装可执行文件失败: %v", err)
		return StateError, fmt.Errorf("运行安装可执行文件失败: %w", err)
	}

	// 使用新版本更新 version.json 文件
	if err := app.updateVersionFile(app.updateInfo.NewVersion); err != nil {
		app.logger.Warn("更新版本文件失败: %v", err)
		// 这不是关键的，继续
	}

	// 安装后清理 AUTOMAA_UPDATE_TEMP 目录
	if err := os.RemoveAll(tempDir); err != nil {
		app.logger.Warn("清理临时目录失败: %v", err)
		// 这不是关键的，继续
	} else {
		app.logger.Info("清理临时目录: %s", tempDir)
	}

	app.logger.Info("安装成功完成")
	fmt.Println("安装完成")
	fmt.Printf("已更新到版本: %s\n", app.updateInfo.NewVersion)

	return StateCompleted, nil
}

// getCurrentState 线程安全地返回当前状态
func (app *Application) getCurrentState() UpdateState {
	app.stateMutex.RLock()
	defer app.stateMutex.RUnlock()
	return app.currentState
}

// setState 线程安全地设置当前状态
func (app *Application) setState(state UpdateState) {
	app.stateMutex.Lock()
	defer app.stateMutex.Unlock()

	app.logger.Debug("状态转换: %s -> %s", app.currentState.String(), state.String())
	app.currentState = state

	// 如果可用则更新 GUI
	if app.guiManager != nil {
		app.updateGUIStatus(state)
	}
}

// updateGUIStatus 根据当前状态更新 GUI
func (app *Application) updateGUIStatus(state UpdateState) {
	if app.guiManager == nil {
		return
	}

	switch state {
	case StateIdle:
		app.guiManager.UpdateStatus(0, "准备检查更新...")
	case StateChecking:
		app.guiManager.UpdateStatus(1, "正在检查更新...")
	case StateUpdateAvailable:
		if app.updateInfo != nil {
			message := fmt.Sprintf("发现新版本: %s", app.updateInfo.NewVersion)
			app.guiManager.UpdateStatus(2, message)
		}
	case StateDownloading:
		app.guiManager.UpdateStatus(3, "正在下载更新...")
	case StateInstalling:
		app.guiManager.UpdateStatus(4, "正在安装更新...")
	case StateCompleted:
		app.guiManager.UpdateStatus(5, "更新完成")
	case StateError:
		app.guiManager.UpdateStatus(6, "更新失败")
	}
}

// formatBytes 将字节格式化为人类可读格式
func (app *Application) formatBytes(bytes int64) string {
	const unit = 1024
	if bytes < unit {
		return fmt.Sprintf("%d B", bytes)
	}
	div, exp := int64(unit), 0
	for n := bytes / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}
	return fmt.Sprintf("%.1f %cB", float64(bytes)/float64(div), "KMGTPE"[exp])
}

// formatVersionForDisplay 将版本格式转换为用户友好的显示格式
// 例如: "4.4.1.3" -> "4.4.1-beta3", "4.4.1.0" -> "4.4.1"
func (app *Application) formatVersionForDisplay(version string) string {
	// 尝试解析版本
	parsedVersion, err := appversion.ParseVersion(version)
	if err != nil {
		// 如果解析失败，返回原始版本
		return version
	}
	
	// 使用 ToDisplayVersion 方法转换为显示格式
	return parsedVersion.ToDisplayVersion()
}

// handleUserInteraction 处理 GUI 模式的用户交互
func (app *Application) handleUserInteraction(action string) {
	switch action {
	case "confirm_update":
		select {
		case app.userConfirmed <- true:
		default:
		}
	case "cancel_update":
		select {
		case app.userConfirmed <- false:
		default:
		}
	case "check_update":
		// 在 goroutine 中启动更新流程
		app.wg.Add(1)
		go func() {
			defer app.wg.Done()
			if err := app.executeUpdateFlow(); err != nil {
				app.logger.Error("更新流程失败: %v", err)
			}
		}()
	}
}

// updateVersionFile 使用新版本更新目标软件的 version.json 文件
func (app *Application) updateVersionFile(newVersion string) error {
	// 获取当前可执行文件目录（目标软件所在位置）
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("获取可执行文件路径失败: %w", err)
	}
	targetDir := filepath.Dir(exePath)

	// 目标软件版本文件的路径
	versionFilePath := filepath.Join(targetDir, "resources", "version.json")

	// 尝试加载现有版本文件
	versionManager := appversion.NewVersionManager()
	versionInfo, err := versionManager.LoadVersionFromFile()
	if err != nil {
		app.logger.Warn("无法加载现有版本文件，创建新文件: %v", err)
		// 创建基本版本信息结构
		versionInfo = &appversion.VersionInfo{
			MainVersion: newVersion,
			VersionInfo: make(map[string]map[string][]string),
		}
	}

	// 解析新版本以获取正确格式
	parsedVersion, err := appversion.ParseVersion(newVersion)
	if err != nil {
		// 如果无法从 API 响应解析版本，尝试从显示格式提取
		if strings.HasPrefix(newVersion, "v") {
			// 将 "v4.4.1-beta3" 转换为 "4.4.1.3" 格式
			versionStr := strings.TrimPrefix(newVersion, "v")
			if strings.Contains(versionStr, "-beta") {
				parts := strings.Split(versionStr, "-beta")
				if len(parts) == 2 {
					baseVersion := parts[0]
					betaNum := parts[1]
					versionInfo.MainVersion = fmt.Sprintf("%s.%s", baseVersion, betaNum)
				} else {
					versionInfo.MainVersion = versionStr + ".0"
				}
			} else {
				versionInfo.MainVersion = versionStr + ".0"
			}
		} else {
			versionInfo.MainVersion = newVersion
		}
	} else {
		// 使用解析的版本创建正确格式
		versionInfo.MainVersion = parsedVersion.ToVersionString()
	}

	// 如果 resources 目录不存在则创建
	resourcesDir := filepath.Join(targetDir, "resources")
	if err := os.MkdirAll(resourcesDir, 0755); err != nil {
		return fmt.Errorf("创建 resources 目录失败: %w", err)
	}

	// 写入更新的版本文件
	data, err := json.MarshalIndent(versionInfo, "", "    ")
	if err != nil {
		return fmt.Errorf("序列化版本信息失败: %w", err)
	}

	if err := os.WriteFile(versionFilePath, data, 0644); err != nil {
		return fmt.Errorf("写入版本文件失败: %w", err)
	}

	app.logger.Info("更新版本文件: %s -> %s", versionFilePath, versionInfo.MainVersion)
	return nil
}

// handleRunningProcesses 处理正在运行的进程但排除更新器本身
func (app *Application) handleRunningProcesses(targetDir, updaterName string) error {
	app.logger.Info("处理正在运行的进程，排除更新器: %s", updaterName)

	// 获取目标目录中的可执行文件列表
	files, err := os.ReadDir(targetDir)
	if err != nil {
		return fmt.Errorf("读取目标目录失败: %w", err)
	}

	for _, file := range files {
		if file.IsDir() {
			continue
		}

		fileName := file.Name()

		// 跳过更新器本身
		if fileName == updaterName {
			app.logger.Info("跳过更新器文件: %s", fileName)
			continue
		}

		// 只处理 .exe 文件
		if !strings.HasSuffix(strings.ToLower(fileName), ".exe") {
			continue
		}

		// 处理此可执行文件
		if err := app.installManager.HandleRunningProcess(fileName); err != nil {
			app.logger.Warn("处理正在运行的进程 %s 失败: %v", fileName, err)
			// 继续处理其他文件，不要让整个过程失败
		}
	}

	return nil
}

// runSetupExecutable 使用适当参数运行安装可执行文件
func (app *Application) runSetupExecutable(setupExePath string) error {
	app.logger.Info("执行安装文件: %s", setupExePath)

	// 获取当前可执行文件目录作为安装目录
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("获取可执行文件路径失败: %w", err)
	}
	installDir := filepath.Dir(exePath)

	// 设置与 Python 实现匹配的命令参数
	args := []string{
		"/SP-",                             // 跳过欢迎页面
		"/SILENT",                          // 静默安装
		"/NOCANCEL",                        // 无取消按钮
		"/FORCECLOSEAPPLICATIONS",          // 强制关闭应用程序
		"/LANG=Chinese",                    // 中文语言
		fmt.Sprintf("/DIR=%s", installDir), // 安装目录
	}

	app.logger.Info("使用参数运行安装程序: %v", args)

	// 使用参数创建命令
	cmd := exec.Command(setupExePath, args...)

	// 设置工作目录为安装文件的目录
	cmd.Dir = filepath.Dir(setupExePath)

	// 运行命令并等待完成
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("执行安装程序失败: %w", err)
	}

	app.logger.Info("安装可执行文件成功完成")
	return nil
}

// AutoMAAConfig 表示 config/config.json 的结构
type AutoMAAConfig struct {
	Update struct {
		UpdateType string `json:"UpdateType"`
	} `json:"Update"`
}

// loadChannelFromConfig 从 config/config.json 加载更新渠道
func (app *Application) loadChannelFromConfig() string {
	// 获取当前可执行文件目录
	exePath, err := os.Executable()
	if err != nil {
		app.logger.Warn("获取可执行文件路径失败: %v", err)
		return "stable"
	}

	configPath := filepath.Join(filepath.Dir(exePath), "config", "config.json")

	// 检查配置文件是否存在
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		app.logger.Info("配置文件未找到: %s，使用默认渠道", configPath)
		return "stable"
	}

	// 读取配置文件
	data, err := os.ReadFile(configPath)
	if err != nil {
		app.logger.Warn("读取配置文件失败: %v，使用默认渠道", err)
		return "stable"
	}

	// 解析 JSON
	var config AutoMAAConfig
	if err := json.Unmarshal(data, &config); err != nil {
		app.logger.Warn("解析配置文件失败: %v，使用默认渠道", err)
		return "stable"
	}

	// 获取更新渠道
	updateType := config.Update.UpdateType
	if updateType == "" {
		app.logger.Info("配置中未找到 UpdateType，使用默认渠道")
		return "stable"
	}

	app.logger.Info("从配置加载更新渠道: %s", updateType)
	return updateType
}
