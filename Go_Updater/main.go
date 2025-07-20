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

	"lightweight-updater/api"
	"lightweight-updater/config"
	"lightweight-updater/download"
	"lightweight-updater/errors"
	"lightweight-updater/install"
	"lightweight-updater/logger"
	appversion "lightweight-updater/version"
)

// UpdateState represents the current state of the update process
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

// String returns the string representation of the update state
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

// GUIManager interface for optional GUI functionality
type GUIManager interface {
	ShowMainWindow()
	UpdateStatus(status int, message string)
	ShowProgress(percentage float64)
	ShowError(errorMsg string)
	Close()
}

// UpdateInfo contains information about an available update
type UpdateInfo struct {
	CurrentVersion string
	NewVersion     string
	DownloadURL    string
	ReleaseNotes   string
	IsAvailable    bool
}

// Application represents the main application instance
type Application struct {
	config         *config.Config
	configManager  config.ConfigManager
	apiClient      api.MirrorClient
	downloadManager download.DownloadManager
	installManager install.InstallManager
	guiManager     GUIManager
	logger         logger.Logger
	errorHandler   errors.ErrorHandler
	ctx            context.Context
	cancel         context.CancelFunc
	wg             sync.WaitGroup
	
	// Update flow state
	currentState   UpdateState
	stateMutex     sync.RWMutex
	updateInfo     *UpdateInfo
	userConfirmed  chan bool
}

// Command line flags
var (
	configPath     = flag.String("config", "", "Path to configuration file")
	logLevel       = flag.String("log-level", "info", "Log level (debug, info, warn, error)")
	noGUI          = flag.Bool("no-gui", false, "Run without GUI (command line mode)")
	version        = flag.Bool("version", false, "Show version information")
	help           = flag.Bool("help", false, "Show help information")
	channel        = flag.String("channel", "", "Update channel (stable or beta)")
	currentVersion = flag.String("current-version", "", "Current version to check against")
	cdk            = flag.String("cdk", "", "CDK for MirrorChyan download")
)

// Version information is now handled by the version package

func main() {
	// Parse command line arguments
	flag.Parse()

	// Show version information
	if *version {
		showVersion()
		return
	}

	// Show help information
	if *help {
		showHelp()
		return
	}

	// Check for single instance
	if err := ensureSingleInstance(); err != nil {
		fmt.Fprintf(os.Stderr, "Another instance is already running: %v\n", err)
		os.Exit(1)
	}

	// Initialize application
	app, err := initializeApplication()
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to initialize application: %v\n", err)
		os.Exit(1)
	}
	defer app.cleanup()

	// Handle cleanup on process marked files on startup
	if err := app.handleStartupCleanup(); err != nil {
		app.logger.Warn("Failed to cleanup marked files: %v", err)
	}

	// Setup signal handling
	app.setupSignalHandling()

	// Start the application
	if err := app.run(); err != nil {
		app.logger.Error("Application error: %v", err)
		os.Exit(1)
	}
}

// initializeApplication initializes all application components
func initializeApplication() (*Application, error) {
	// Create context for graceful shutdown
	ctx, cancel := context.WithCancel(context.Background())

	// Initialize logger first
	loggerConfig := logger.DefaultLoggerConfig()
	
	// Set log level from command line
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
		// Fallback to console logger
		appLogger = logger.NewConsoleLogger(os.Stdout)
	} else {
		appLogger = fileLogger
	}

	appLogger.Info("Initializing AUTO_MAA_Go_Updater v%s", appversion.Version)

	// Initialize configuration manager
	var configManager config.ConfigManager
	if *configPath != "" {
		// Custom config path not implemented in the config package yet
		// For now, use default manager
		configManager = config.NewConfigManager()
		appLogger.Warn("Custom config path not fully supported yet, using default")
	} else {
		configManager = config.NewConfigManager()
	}

	// Load configuration
	cfg, err := configManager.Load()
	if err != nil {
		appLogger.Error("Failed to load configuration: %v", err)
		return nil, fmt.Errorf("failed to load configuration: %w", err)
	}

	appLogger.Info("Configuration loaded successfully")

	// Initialize API client
	apiClient := api.NewClient()

	// Initialize download manager
	downloadManager := download.NewManager()

	// Initialize install manager
	installManager := install.NewManager()

	// Initialize error handler
	errorHandler := errors.NewDefaultErrorHandler()

	// Initialize GUI manager (if not in no-gui mode)
	var guiManager GUIManager
	if !*noGUI {
		// GUI will be implemented when GUI dependencies are available
		appLogger.Info("GUI mode requested but not available in this build")
		guiManager = nil
	} else {
		appLogger.Info("Running in no-GUI mode")
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

	appLogger.Info("Application initialized successfully")
	return app, nil
}

// run starts the main application logic
func (app *Application) run() error {
	app.logger.Info("Starting application")

	if app.guiManager != nil {
		// Run with GUI
		return app.runWithGUI()
	} else {
		// Run in command line mode
		return app.runCommandLine()
	}
}

// runWithGUI runs the application with GUI
func (app *Application) runWithGUI() error {
	app.logger.Info("Starting GUI mode")
	
	// Set up GUI callbacks
	app.setupGUICallbacks()
	
	// Show main window (this will block until window is closed)
	app.guiManager.ShowMainWindow()
	
	return nil
}

// runCommandLine runs the application in command line mode
func (app *Application) runCommandLine() error {
	app.logger.Info("Starting command line mode")
	
	// Start the complete update flow
	return app.executeUpdateFlow()
}

// setupGUICallbacks sets up callbacks for GUI interactions
func (app *Application) setupGUICallbacks() {
	if app.guiManager == nil {
		return
	}

	// GUI callbacks will be implemented when GUI is available
	app.logger.Info("GUI callbacks setup requested but GUI not available")
	
	// For now, we'll set up basic interaction handling
	// The actual GUI integration will be completed when GUI dependencies are resolved
}

// handleStartupCleanup handles cleanup of files marked for deletion on startup
func (app *Application) handleStartupCleanup() error {
	app.logger.Info("Performing startup cleanup")
	
	// Get current executable directory
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("failed to get executable path: %w", err)
	}
	
	exeDir := filepath.Dir(exePath)
	
	// Delete files marked for deletion
	if installMgr, ok := app.installManager.(*install.Manager); ok {
		if err := installMgr.DeleteMarkedFiles(exeDir); err != nil {
			return fmt.Errorf("failed to delete marked files: %w", err)
		}
	}
	
	app.logger.Info("Startup cleanup completed")
	return nil
}

// setupSignalHandling sets up graceful shutdown on system signals
func (app *Application) setupSignalHandling() {
	sigChan := make(chan os.Signal, 1)
	signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
	
	go func() {
		sig := <-sigChan
		app.logger.Info("Received signal: %v", sig)
		app.logger.Info("Initiating graceful shutdown...")
		app.cancel()
	}()
}

// cleanup performs application cleanup
func (app *Application) cleanup() {
	app.logger.Info("Cleaning up application resources")
	
	// Cancel context to stop all operations
	app.cancel()
	
	// Wait for all goroutines to finish
	app.wg.Wait()
	
	// Cleanup install manager temporary directories
	if installMgr, ok := app.installManager.(*install.Manager); ok {
		if err := installMgr.CleanupAllTempDirs(); err != nil {
			app.logger.Error("Failed to cleanup temp directories: %v", err)
		}
	}
	
	app.logger.Info("Application cleanup completed")
	
	// Close logger last
	if err := app.logger.Close(); err != nil {
		fmt.Fprintf(os.Stderr, "Failed to close logger: %v\n", err)
	}
}

// ensureSingleInstance ensures only one instance of the application is running
func ensureSingleInstance() error {
	// Create a lock file in temp directory
	tempDir := os.TempDir()
	lockFile := filepath.Join(tempDir, "lightweight-updater.lock")
	
	// Try to create the lock file exclusively
	file, err := os.OpenFile(lockFile, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0644)
	if err != nil {
		if os.IsExist(err) {
			// Check if the process is still running
			if isProcessRunning(lockFile) {
				return fmt.Errorf("another instance is already running")
			}
			// Remove stale lock file and try again
			os.Remove(lockFile)
			return ensureSingleInstance()
		}
		return fmt.Errorf("failed to create lock file: %w", err)
	}
	
	// Write current process ID to lock file
	fmt.Fprintf(file, "%d", os.Getpid())
	file.Close()
	
	// Remove lock file on exit
	go func() {
		sigChan := make(chan os.Signal, 1)
		signal.Notify(sigChan, syscall.SIGINT, syscall.SIGTERM)
		<-sigChan
		os.Remove(lockFile)
	}()
	
	return nil
}

// isProcessRunning checks if the process in the lock file is still running
func isProcessRunning(lockFile string) bool {
	data, err := os.ReadFile(lockFile)
	if err != nil {
		return false
	}
	
	var pid int
	if _, err := fmt.Sscanf(string(data), "%d", &pid); err != nil {
		return false
	}
	
	// Check if process exists (Windows specific)
	process, err := os.FindProcess(pid)
	if err != nil {
		return false
	}
	
	// On Windows, FindProcess always succeeds, so we need to check differently
	// Try to send signal 0 to check if process exists
	err = process.Signal(syscall.Signal(0))
	return err == nil
}

// showVersion displays version information
func showVersion() {
	fmt.Printf("AUTO_MAA_Go_Updater\n")
	fmt.Printf("Version: %s\n", appversion.Version)
	fmt.Printf("Build Time: %s\n", appversion.BuildTime)
	fmt.Printf("Git Commit: %s\n", appversion.GitCommit)
}

// showHelp displays help information
func showHelp() {
	fmt.Printf("AUTO_MAA_Go_Updater - AUTO_MAA 轻量级更新器\n\n")
	fmt.Printf("Usage: %s [options]\n\n", os.Args[0])
	fmt.Printf("Options:\n")
	flag.PrintDefaults()
	fmt.Printf("\nExamples:\n")
	fmt.Printf("  %s                    # Run with GUI\n", os.Args[0])
	fmt.Printf("  %s -no-gui           # Run in command line mode\n", os.Args[0])
	fmt.Printf("  %s -log-level debug  # Run with debug logging\n", os.Args[0])
	fmt.Printf("  %s -version          # Show version information\n", os.Args[0])
}

// executeUpdateFlow executes the complete update flow with state machine management
func (app *Application) executeUpdateFlow() error {
	app.logger.Info("Starting update flow execution")
	
	// Execute the state machine
	for {
		select {
		case <-app.ctx.Done():
			app.logger.Info("Update flow cancelled")
			return app.ctx.Err()
		default:
		}
		
		// Get current state
		state := app.getCurrentState()
		app.logger.Debug("Current state: %s", state.String())
		
		// Execute state logic
		nextState, err := app.executeState(state)
		if err != nil {
			app.logger.Error("State execution failed: %v", err)
			app.setState(StateError)
			return err
		}
		
		// Check if we're done
		if nextState == StateCompleted || nextState == StateError {
			app.setState(nextState)
			break
		}
		
		// Transition to next state
		app.setState(nextState)
	}
	
	finalState := app.getCurrentState()
	app.logger.Info("Update flow completed with state: %s", finalState.String())
	
	if finalState == StateError {
		return fmt.Errorf("update flow failed")
	}
	
	return nil
}

// executeState executes the logic for the current state and returns the next state
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
		return StateError, fmt.Errorf("unknown state: %s", state.String())
	}
}

// executeIdleState handles the idle state
func (app *Application) executeIdleState() (UpdateState, error) {
	app.logger.Info("Starting update check...")
	fmt.Println("正在检查更新...")
	return StateChecking, nil
}

// executeCheckingState handles the checking state
func (app *Application) executeCheckingState() (UpdateState, error) {
	app.logger.Info("Checking for updates")
	
	// Determine version and channel to use
	var currentVer, updateChannel, cdkToUse string
	var err error
	
	// Priority: command line args > version file > config
	if *currentVersion != "" {
		currentVer = *currentVersion
		app.logger.Info("Using current version from command line: %s", currentVer)
	} else {
		// Try to load version from resources/version.json
		versionManager := appversion.NewVersionManager()
		versionInfo, err := versionManager.LoadVersionFromFile()
		if err != nil {
			app.logger.Warn("Failed to load version from file: %v, using config version", err)
			currentVer = app.config.CurrentVersion
		} else {
			currentVer = versionInfo.MainVersion
			app.logger.Info("Using current version from version file: %s", currentVer)
		}
	}
	
	// Determine channel
	if *channel != "" {
		updateChannel = *channel
		app.logger.Info("Using channel from command line: %s", updateChannel)
	} else {
		// Try to load channel from config.json
		updateChannel = app.loadChannelFromConfig()
		app.logger.Info("Using channel from config: %s", updateChannel)
	}
	
	// Determine CDK to use
	if *cdk != "" {
		cdkToUse = *cdk
		app.logger.Info("Using CDK from command line")
	} else {
		// Get CDK from config
		cdkToUse, err = app.config.GetCDK()
		if err != nil {
			app.logger.Warn("Failed to get CDK from config: %v", err)
			cdkToUse = "" // Continue without CDK
		}
	}
	
	// Prepare API parameters
	params := api.UpdateCheckParams{
		ResourceID:     "AUTO_MAA", // Fixed resource ID for AUTO_MAA
		CurrentVersion: currentVer,
		Channel:        updateChannel,
		CDK:            cdkToUse,
		UserAgent:      app.config.UserAgent,
	}
	
	// Call MirrorChyan API to check for updates
	response, err := app.apiClient.CheckUpdate(params)
	if err != nil {
		app.logger.Error("Failed to check for updates: %v", err)
		fmt.Printf("检查更新失败: %v\n", err)
		return StateError, fmt.Errorf("failed to check for updates: %w", err)
	}
	
	// Check if update is available
	isUpdateAvailable := app.apiClient.IsUpdateAvailable(response, currentVer)
	
	if !isUpdateAvailable {
		app.logger.Info("No update available")
		fmt.Println("当前已是最新版本")
		return StateCompleted, nil
	}
	
	// Determine download URL
	var downloadURL string
	if response.Data.URL != "" {
		// Use CDK download URL from MirrorChyan
		downloadURL = response.Data.URL
		app.logger.Info("Using CDK download URL from MirrorChyan")
	} else {
		// Use official download site
		downloadURL = app.apiClient.GetOfficialDownloadURL(response.Data.VersionName)
		app.logger.Info("Using official download URL: %s", downloadURL)
	}
	
	// Store update information
	app.updateInfo = &UpdateInfo{
		CurrentVersion: currentVer,
		NewVersion:     response.Data.VersionName,
		DownloadURL:    downloadURL,
		ReleaseNotes:   response.Data.ReleaseNote,
		IsAvailable:    true,
	}
	
	app.logger.Info("Update available: %s -> %s", currentVer, response.Data.VersionName)
	fmt.Printf("发现新版本: %s -> %s\n", currentVer, response.Data.VersionName)
	
	// if response.Data.ReleaseNote != "" {
	// 	fmt.Printf("更新内容: %s\n", response.Data.ReleaseNote)
	// }
	
	return StateUpdateAvailable, nil
}

// executeUpdateAvailableState handles the update available state
func (app *Application) executeUpdateAvailableState() (UpdateState, error) {
	app.logger.Info("Update available, starting download automatically")
	
	// Automatically start download without user confirmation
	fmt.Println("开始下载更新...")
	return StateDownloading, nil
}

// executeDownloadingState handles the downloading state
func (app *Application) executeDownloadingState() (UpdateState, error) {
	app.logger.Info("Starting download")
	
	if app.updateInfo == nil || app.updateInfo.DownloadURL == "" {
		return StateError, fmt.Errorf("no download URL available")
	}
	
	// Get current executable directory
	exePath, err := os.Executable()
	if err != nil {
		return StateError, fmt.Errorf("failed to get executable path: %w", err)
	}
	exeDir := filepath.Dir(exePath)
	
	// Create AUTOMAA_UPDATE_TEMP directory for download
	tempDir := filepath.Join(exeDir, "AUTOMAA_UPDATE_TEMP")
	if err := os.MkdirAll(tempDir, 0755); err != nil {
		return StateError, fmt.Errorf("failed to create temp directory: %w", err)
	}
	
	// Download file
	downloadPath := filepath.Join(tempDir, "update.zip")
	
	fmt.Println("正在下载更新包...")
	
	// Create progress callback
	progressCallback := func(progress download.DownloadProgress) {
		if progress.TotalBytes > 0 {
			fmt.Printf("\r下载进度: %.1f%% (%s/s)", 
				progress.Percentage, 
				app.formatBytes(progress.Speed))
		}
	}
	
	// Download the update file
	downloadErr := app.downloadManager.Download(app.updateInfo.DownloadURL, downloadPath, progressCallback)
	
	fmt.Println() // New line after progress
	
	if downloadErr != nil {
		app.logger.Error("Download failed: %v", downloadErr)
		fmt.Printf("下载失败: %v\n", downloadErr)
		return StateError, fmt.Errorf("download failed: %w", downloadErr)
	}
	
	app.logger.Info("Download completed successfully")
	fmt.Println("下载完成")
	
	// Store download path for installation
	app.updateInfo.DownloadURL = downloadPath
	
	return StateInstalling, nil
}

// executeInstallingState handles the installing state
func (app *Application) executeInstallingState() (UpdateState, error) {
	app.logger.Info("Starting installation")
	fmt.Println("正在安装更新...")
	
	if app.updateInfo == nil || app.updateInfo.DownloadURL == "" {
		return StateError, fmt.Errorf("no download file available")
	}
	
	downloadPath := app.updateInfo.DownloadURL
	
	// Create temporary directory for extraction
	tempDir, err := app.installManager.CreateTempDir()
	if err != nil {
		return StateError, fmt.Errorf("failed to create temp directory: %w", err)
	}
	
	// Extract the downloaded zip file
	app.logger.Info("Extracting update package")
	if err := app.installManager.ExtractZip(downloadPath, tempDir); err != nil {
		app.logger.Error("Failed to extract zip: %v", err)
		return StateError, fmt.Errorf("failed to extract update package: %w", err)
	}
	
	// Process changes.json if it exists (for future use)
	changesPath := filepath.Join(tempDir, "changes.json")
	_, err = app.installManager.ProcessChanges(changesPath)
	if err != nil {
		app.logger.Warn("Failed to process changes (not critical): %v", err)
		// This is not critical for AUTO_MAA-Setup.exe installation
	}
	
	// Get current executable directory
	exePath, err := os.Executable()
	if err != nil {
		return StateError, fmt.Errorf("failed to get executable path: %w", err)
	}
	targetDir := filepath.Dir(exePath)
	
	// Handle running processes (but skip the updater itself)
	updaterName := filepath.Base(exePath)
	if err := app.handleRunningProcesses(targetDir, updaterName); err != nil {
		app.logger.Warn("Failed to handle running processes: %v", err)
		// Continue with installation, this is not critical
	}
	
	// Look for AUTO_MAA-Setup.exe in the extracted files
	setupExePath := filepath.Join(tempDir, "AUTO_MAA-Setup.exe")
	if _, err := os.Stat(setupExePath); err != nil {
		app.logger.Error("AUTO_MAA-Setup.exe not found in update package: %v", err)
		return StateError, fmt.Errorf("AUTO_MAA-Setup.exe not found in update package: %w", err)
	}
	
	// Run the setup executable
	app.logger.Info("Running AUTO_MAA-Setup.exe")
	fmt.Println("正在运行安装程序...")
	
	if err := app.runSetupExecutable(setupExePath); err != nil {
		app.logger.Error("Failed to run setup executable: %v", err)
		return StateError, fmt.Errorf("failed to run setup executable: %w", err)
	}
	
	// Update the version.json file with new version
	if err := app.updateVersionFile(app.updateInfo.NewVersion); err != nil {
		app.logger.Warn("Failed to update version file: %v", err)
		// This is not critical, continue
	}
	
	// Clean up AUTOMAA_UPDATE_TEMP directory after installation
	if err := os.RemoveAll(tempDir); err != nil {
		app.logger.Warn("Failed to cleanup temp directory: %v", err)
		// This is not critical, continue
	} else {
		app.logger.Info("Cleaned up temp directory: %s", tempDir)
	}
	
	app.logger.Info("Installation completed successfully")
	fmt.Println("安装完成")
	fmt.Printf("已更新到版本: %s\n", app.updateInfo.NewVersion)
	
	return StateCompleted, nil
}

// getCurrentState returns the current state thread-safely
func (app *Application) getCurrentState() UpdateState {
	app.stateMutex.RLock()
	defer app.stateMutex.RUnlock()
	return app.currentState
}

// setState sets the current state thread-safely
func (app *Application) setState(state UpdateState) {
	app.stateMutex.Lock()
	defer app.stateMutex.Unlock()
	
	app.logger.Debug("State transition: %s -> %s", app.currentState.String(), state.String())
	app.currentState = state
	
	// Update GUI if available
	if app.guiManager != nil {
		app.updateGUIStatus(state)
	}
}

// updateGUIStatus updates the GUI based on the current state
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

// formatBytes formats bytes into human readable format
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

// handleUserInteraction handles user interaction for GUI mode
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
		// Start update flow in a goroutine
		app.wg.Add(1)
		go func() {
			defer app.wg.Done()
			if err := app.executeUpdateFlow(); err != nil {
				app.logger.Error("Update flow failed: %v", err)
			}
		}()
	}
}

// updateVersionFile updates the target software's version.json file with the new version
func (app *Application) updateVersionFile(newVersion string) error {
	// Get current executable directory (where the target software is located)
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("failed to get executable path: %w", err)
	}
	targetDir := filepath.Dir(exePath)
	
	// Path to the target software's version file
	versionFilePath := filepath.Join(targetDir, "resources", "version.json")
	
	// Try to load existing version file
	versionManager := appversion.NewVersionManager()
	versionInfo, err := versionManager.LoadVersionFromFile()
	if err != nil {
		app.logger.Warn("Could not load existing version file, creating new one: %v", err)
		// Create a basic version info structure
		versionInfo = &appversion.VersionInfo{
			MainVersion: newVersion,
			VersionInfo: make(map[string]map[string][]string),
		}
	}
	
	// Parse the new version to get the proper format
	parsedVersion, err := appversion.ParseVersion(newVersion)
	if err != nil {
		// If we can't parse the version from API response, try to extract from display format
		if strings.HasPrefix(newVersion, "v") {
			// Convert "v4.4.1-beta3" to "4.4.1.3" format
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
		// Use the parsed version to create the proper format
		versionInfo.MainVersion = parsedVersion.ToVersionString()
	}
	
	// Create resources directory if it doesn't exist
	resourcesDir := filepath.Join(targetDir, "resources")
	if err := os.MkdirAll(resourcesDir, 0755); err != nil {
		return fmt.Errorf("failed to create resources directory: %w", err)
	}
	
	// Write updated version file
	data, err := json.MarshalIndent(versionInfo, "", "    ")
	if err != nil {
		return fmt.Errorf("failed to marshal version info: %w", err)
	}
	
	if err := os.WriteFile(versionFilePath, data, 0644); err != nil {
		return fmt.Errorf("failed to write version file: %w", err)
	}
	
	app.logger.Info("Updated version file: %s -> %s", versionFilePath, versionInfo.MainVersion)
	return nil
}

// handleRunningProcesses handles running processes but excludes the updater itself
func (app *Application) handleRunningProcesses(targetDir, updaterName string) error {
	app.logger.Info("Handling running processes, excluding updater: %s", updaterName)
	
	// Get list of executable files in the target directory
	files, err := os.ReadDir(targetDir)
	if err != nil {
		return fmt.Errorf("failed to read target directory: %w", err)
	}
	
	for _, file := range files {
		if file.IsDir() {
			continue
		}
		
		fileName := file.Name()
		
		// Skip the updater itself
		if fileName == updaterName {
			app.logger.Info("Skipping updater file: %s", fileName)
			continue
		}
		
		// Only handle .exe files
		if !strings.HasSuffix(strings.ToLower(fileName), ".exe") {
			continue
		}
		
		// Handle this executable
		if err := app.installManager.HandleRunningProcess(fileName); err != nil {
			app.logger.Warn("Failed to handle running process %s: %v", fileName, err)
			// Continue with other files, don't fail the entire process
		}
	}
	
	return nil
}

// runSetupExecutable runs the setup executable with proper parameters
func (app *Application) runSetupExecutable(setupExePath string) error {
	app.logger.Info("Executing setup file: %s", setupExePath)
	
	// Get current executable directory as installation directory
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("failed to get executable path: %w", err)
	}
	installDir := filepath.Dir(exePath)
	
	// Setup command with parameters matching Python implementation
	args := []string{
		"/SP-",                           // Skip welcome page
		"/SILENT",                        // Silent installation
		"/NOCANCEL",                      // No cancel button
		"/FORCECLOSEAPPLICATIONS",        // Force close applications
		"/LANG=Chinese",                  // Chinese language
		fmt.Sprintf("/DIR=%s", installDir), // Installation directory
	}
	
	app.logger.Info("Running setup with args: %v", args)
	
	// Create command with arguments
	cmd := exec.Command(setupExePath, args...)
	
	// Set working directory to the setup file's directory
	cmd.Dir = filepath.Dir(setupExePath)
	
	// Run the command and wait for it to complete
	if err := cmd.Run(); err != nil {
		return fmt.Errorf("failed to execute setup: %w", err)
	}
	
	app.logger.Info("Setup executable completed successfully")
	return nil
}

// AutoMAAConfig represents the structure of config/config.json
type AutoMAAConfig struct {
	Update struct {
		UpdateType string `json:"UpdateType"`
	} `json:"Update"`
}

// loadChannelFromConfig loads the update channel from config/config.json
func (app *Application) loadChannelFromConfig() string {
	// Get current executable directory
	exePath, err := os.Executable()
	if err != nil {
		app.logger.Warn("Failed to get executable path: %v", err)
		return "stable"
	}
	
	configPath := filepath.Join(filepath.Dir(exePath), "config", "config.json")
	
	// Check if config file exists
	if _, err := os.Stat(configPath); os.IsNotExist(err) {
		app.logger.Info("Config file not found: %s, using default channel", configPath)
		return "stable"
	}
	
	// Read config file
	data, err := os.ReadFile(configPath)
	if err != nil {
		app.logger.Warn("Failed to read config file: %v, using default channel", err)
		return "stable"
	}
	
	// Parse JSON
	var config AutoMAAConfig
	if err := json.Unmarshal(data, &config); err != nil {
		app.logger.Warn("Failed to parse config file: %v, using default channel", err)
		return "stable"
	}
	
	// Get update channel
	updateType := config.Update.UpdateType
	if updateType == "" {
		app.logger.Info("UpdateType not found in config, using default channel")
		return "stable"
	}
	
	app.logger.Info("Loaded update channel from config: %s", updateType)
	return updateType
}