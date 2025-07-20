package gui

import (
	"fmt"
	"fyne.io/fyne/v2/app"
	"fyne.io/fyne/v2/container"
	"fyne.io/fyne/v2/dialog"
	"fyne.io/fyne/v2/widget"
	"fyne.io/fyne/v2/theme"
	"fyne.io/fyne/v2"
)

// UpdateStatus represents the current status of the update process
type UpdateStatus int

const (
	StatusChecking UpdateStatus = iota
	StatusUpdateAvailable
	StatusDownloading
	StatusInstalling
	StatusCompleted
	StatusError
)

// Config represents the configuration structure for the GUI
type Config struct {
	ResourceID     string
	CurrentVersion string
	CDK            string
	UserAgent      string
	BackupURL      string
}

// GUIManager interface defines the methods for GUI management
type GUIManager interface {
	ShowMainWindow()
	UpdateStatus(status UpdateStatus, message string)
	ShowProgress(percentage float64)
	ShowError(errorMsg string)
	ShowConfigDialog() (*Config, error)
	Close()
}

// Manager implements the GUIManager interface
type Manager struct {
	app           fyne.App
	window        fyne.Window
	statusLabel   *widget.Label
	progressBar   *widget.ProgressBar
	actionButton  *widget.Button
	versionLabel  *widget.Label
	releaseNotes  *widget.RichText
	currentStatus UpdateStatus
	onCheckUpdate func()
	onCancel      func()
}

// NewManager creates a new GUI manager instance
func NewManager() *Manager {
	a := app.New()
	a.SetIcon(theme.ComputerIcon())
	
	w := a.NewWindow("轻量级更新器")
	w.Resize(fyne.NewSize(500, 400))
	w.SetFixedSize(false)
	w.CenterOnScreen()
	
	return &Manager{
		app:    a,
		window: w,
	}
}

// SetCallbacks sets the callback functions for user actions
func (m *Manager) SetCallbacks(onCheckUpdate, onCancel func()) {
	m.onCheckUpdate = onCheckUpdate
	m.onCancel = onCancel
}

// ShowMainWindow displays the main application window
func (m *Manager) ShowMainWindow() {
	// Create UI components
	m.createUIComponents()
	
	// Create main layout
	content := m.createMainLayout()
	
	m.window.SetContent(content)
	m.window.ShowAndRun()
}

// createUIComponents initializes all UI components
func (m *Manager) createUIComponents() {
	// Status label
	m.statusLabel = widget.NewLabel("准备检查更新...")
	m.statusLabel.Alignment = fyne.TextAlignCenter
	
	// Progress bar
	m.progressBar = widget.NewProgressBar()
	m.progressBar.Hide()
	
	// Version label
	m.versionLabel = widget.NewLabel("当前版本: 未知")
	m.versionLabel.TextStyle = fyne.TextStyle{Italic: true}
	
	// Release notes
	m.releaseNotes = widget.NewRichText()
	m.releaseNotes.Hide()
	
	// Action button
	m.actionButton = widget.NewButton("检查更新", func() {
		if m.onCheckUpdate != nil {
			m.onCheckUpdate()
		}
	})
	m.actionButton.Importance = widget.HighImportance
}

// createMainLayout creates the main window layout
func (m *Manager) createMainLayout() *container.VBox {
	// Header section
	header := container.NewVBox(
		widget.NewCard("", "", container.NewVBox(
			widget.NewLabelWithStyle("轻量级更新器", fyne.TextAlignCenter, fyne.TextStyle{Bold: true}),
			m.versionLabel,
		)),
	)
	
	// Status section
	statusSection := container.NewVBox(
		m.statusLabel,
		m.progressBar,
	)
	
	// Release notes section
	releaseNotesCard := widget.NewCard("更新日志", "", container.NewScroll(m.releaseNotes))
	releaseNotesCard.Hide()
	
	// Button section
	buttonSection := container.NewHBox(
		widget.NewButton("配置", func() {
			m.showConfigDialog()
		}),
		widget.NewSpacer(),
		m.actionButton,
	)
	
	// Main layout
	return container.NewVBox(
		header,
		widget.NewSeparator(),
		statusSection,
		releaseNotesCard,
		widget.NewSeparator(),
		buttonSection,
	)
}

// UpdateStatus updates the current status and UI accordingly
func (m *Manager) UpdateStatus(status UpdateStatus, message string) {
	m.currentStatus = status
	m.statusLabel.SetText(message)
	
	switch status {
	case StatusChecking:
		m.actionButton.SetText("检查中...")
		m.actionButton.Disable()
		m.progressBar.Hide()
		
	case StatusUpdateAvailable:
		m.actionButton.SetText("开始更新")
		m.actionButton.Enable()
		m.progressBar.Hide()
		
	case StatusDownloading:
		m.actionButton.SetText("下载中...")
		m.actionButton.Disable()
		m.progressBar.Show()
		
	case StatusInstalling:
		m.actionButton.SetText("安装中...")
		m.actionButton.Disable()
		m.progressBar.Show()
		
	case StatusCompleted:
		m.actionButton.SetText("完成")
		m.actionButton.Enable()
		m.progressBar.Hide()
		
	case StatusError:
		m.actionButton.SetText("重试")
		m.actionButton.Enable()
		m.progressBar.Hide()
	}
}

// ShowProgress updates the progress bar
func (m *Manager) ShowProgress(percentage float64) {
	if percentage < 0 {
		percentage = 0
	}
	if percentage > 100 {
		percentage = 100
	}
	
	m.progressBar.SetValue(percentage / 100.0)
	m.progressBar.Show()
}

// ShowError displays an error dialog
func (m *Manager) ShowError(errorMsg string) {
	dialog.ShowError(fmt.Errorf(errorMsg), m.window)
}

// ShowConfigDialog displays the configuration dialog
func (m *Manager) ShowConfigDialog() (*Config, error) {
	return m.showConfigDialog()
}

// showConfigDialog creates and shows the configuration dialog
func (m *Manager) showConfigDialog() (*Config, error) {
	// Create form entries
	resourceIDEntry := widget.NewEntry()
	resourceIDEntry.SetPlaceHolder("例如: M9A")
	
	versionEntry := widget.NewEntry()
	versionEntry.SetPlaceHolder("例如: v1.0.0")
	
	cdkEntry := widget.NewPasswordEntry()
	cdkEntry.SetPlaceHolder("输入您的CDK（可选）")
	
	userAgentEntry := widget.NewEntry()
	userAgentEntry.SetText("LightweightUpdater/1.0")
	
	backupURLEntry := widget.NewEntry()
	backupURLEntry.SetPlaceHolder("备用下载地址（可选）")
	
	// Create form
	form := &widget.Form{
		Items: []*widget.FormItem{
			{Text: "资源ID:", Widget: resourceIDEntry},
			{Text: "当前版本:", Widget: versionEntry},
			{Text: "CDK:", Widget: cdkEntry},
			{Text: "用户代理:", Widget: userAgentEntry},
			{Text: "备用下载地址:", Widget: backupURLEntry},
		},
	}
	
	// Create result channel
	resultChan := make(chan *Config, 1)
	errorChan := make(chan error, 1)
	
	// Create dialog
	configDialog := dialog.NewCustomConfirm(
		"配置设置",
		"保存",
		"取消",
		form,
		func(confirmed bool) {
			if confirmed {
				config := &Config{
					ResourceID:     resourceIDEntry.Text,
					CurrentVersion: versionEntry.Text,
					CDK:            cdkEntry.Text,
					UserAgent:      userAgentEntry.Text,
					BackupURL:      backupURLEntry.Text,
				}
				
				// Basic validation
				if config.ResourceID == "" {
					errorChan <- fmt.Errorf("资源ID不能为空")
					return
				}
				if config.CurrentVersion == "" {
					errorChan <- fmt.Errorf("当前版本不能为空")
					return
				}
				
				resultChan <- config
			} else {
				errorChan <- fmt.Errorf("用户取消了配置")
			}
		},
		m.window,
	)
	
	// Add help text
	helpText := widget.NewRichTextFromMarkdown(`
**配置说明:**
- **资源ID**: Mirror酱服务中的资源标识符
- **当前版本**: 当前软件的版本号
- **CDK**: Mirror酱服务的访问密钥（可选，提供更好的下载体验）
- **用户代理**: HTTP请求的用户代理字符串
- **备用下载地址**: 当Mirror酱服务不可用时的备用下载地址

如需获取CDK，请访问 [Mirror酱官网](https://mirrorchyan.com)
`)
	
	// Create container with help text
	dialogContent := container.NewVBox(
		form,
		widget.NewSeparator(),
		helpText,
	)
	
	configDialog.SetContent(dialogContent)
	configDialog.Resize(fyne.NewSize(600, 500))
	configDialog.Show()
	
	// Wait for result
	select {
	case config := <-resultChan:
		return config, nil
	case err := <-errorChan:
		return nil, err
	}
}

// SetVersionInfo updates the version display
func (m *Manager) SetVersionInfo(version string) {
	m.versionLabel.SetText(fmt.Sprintf("当前版本: %s", version))
}

// ShowReleaseNotes displays the release notes
func (m *Manager) ShowReleaseNotes(notes string) {
	if notes != "" {
		m.releaseNotes.ParseMarkdown(notes)
		// Find the release notes card and show it
		if parent := m.window.Content().(*container.VBox); parent != nil {
			for _, obj := range parent.Objects {
				if card, ok := obj.(*widget.Card); ok && card.Title == "更新日志" {
					card.Show()
					break
				}
			}
		}
	}
}

// UpdateStatusWithDetails updates status with detailed information
func (m *Manager) UpdateStatusWithDetails(status UpdateStatus, message string, details map[string]string) {
	m.UpdateStatus(status, message)
	
	// Update version info if provided
	if version, ok := details["version"]; ok {
		m.SetVersionInfo(version)
	}
	
	// Show release notes if provided
	if notes, ok := details["release_notes"]; ok {
		m.ShowReleaseNotes(notes)
	}
	
	// Update progress if provided
	if progress, ok := details["progress"]; ok {
		if p, err := fmt.Sscanf(progress, "%f", new(float64)); err == nil && p == 1 {
			var progressValue float64
			fmt.Sscanf(progress, "%f", &progressValue)
			m.ShowProgress(progressValue)
		}
	}
}

// ShowProgressWithSpeed shows progress with download speed information
func (m *Manager) ShowProgressWithSpeed(percentage float64, speed int64, eta string) {
	m.ShowProgress(percentage)
	
	// Update status with speed and ETA information
	speedText := m.formatSpeed(speed)
	statusText := fmt.Sprintf("下载中... %.1f%% (%s)", percentage, speedText)
	if eta != "" {
		statusText += fmt.Sprintf(" - 剩余时间: %s", eta)
	}
	
	m.statusLabel.SetText(statusText)
}

// formatSpeed formats the download speed for display
func (m *Manager) formatSpeed(bytesPerSecond int64) string {
	if bytesPerSecond < 1024 {
		return fmt.Sprintf("%d B/s", bytesPerSecond)
	} else if bytesPerSecond < 1024*1024 {
		return fmt.Sprintf("%.1f KB/s", float64(bytesPerSecond)/1024)
	} else {
		return fmt.Sprintf("%.1f MB/s", float64(bytesPerSecond)/(1024*1024))
	}
}

// ShowConfirmDialog shows a confirmation dialog
func (m *Manager) ShowConfirmDialog(title, message string, callback func(bool)) {
	dialog.ShowConfirm(title, message, callback, m.window)
}

// ShowInfoDialog shows an information dialog
func (m *Manager) ShowInfoDialog(title, message string) {
	dialog.ShowInformation(title, message, m.window)
}

// ShowUpdateAvailableDialog shows a dialog when update is available
func (m *Manager) ShowUpdateAvailableDialog(currentVersion, newVersion, releaseNotes string, onConfirm func()) {
	content := container.NewVBox(
		widget.NewLabel(fmt.Sprintf("发现新版本: %s", newVersion)),
		widget.NewLabel(fmt.Sprintf("当前版本: %s", currentVersion)),
		widget.NewSeparator(),
	)
	
	if releaseNotes != "" {
		notesWidget := widget.NewRichText()
		notesWidget.ParseMarkdown(releaseNotes)
		
		notesScroll := container.NewScroll(notesWidget)
		notesScroll.SetMinSize(fyne.NewSize(400, 200))
		
		content.Add(widget.NewLabel("更新内容:"))
		content.Add(notesScroll)
	}
	
	dialog.ShowCustomConfirm(
		"发现新版本",
		"立即更新",
		"稍后提醒",
		content,
		func(confirmed bool) {
			if confirmed && onConfirm != nil {
				onConfirm()
			}
		},
		m.window,
	)
}

// SetActionButtonCallback sets the callback for the main action button
func (m *Manager) SetActionButtonCallback(callback func()) {
	if m.actionButton != nil {
		m.actionButton.OnTapped = callback
	}
}

// EnableActionButton enables or disables the action button
func (m *Manager) EnableActionButton(enabled bool) {
	if m.actionButton != nil {
		if enabled {
			m.actionButton.Enable()
		} else {
			m.actionButton.Disable()
		}
	}
}

// SetActionButtonText sets the text of the action button
func (m *Manager) SetActionButtonText(text string) {
	if m.actionButton != nil {
		m.actionButton.SetText(text)
	}
}

// ShowErrorWithRetry shows an error with retry option
func (m *Manager) ShowErrorWithRetry(errorMsg string, onRetry func()) {
	dialog.ShowCustomConfirm(
		"错误",
		"重试",
		"取消",
		widget.NewLabel(errorMsg),
		func(retry bool) {
			if retry && onRetry != nil {
				onRetry()
			}
		},
		m.window,
	)
}

// UpdateProgressBar updates the progress bar with custom styling
func (m *Manager) UpdateProgressBar(percentage float64, color string) {
	m.ShowProgress(percentage)
	// Note: Fyne doesn't support custom colors easily, but we keep the interface for future enhancement
}

// HideProgressBar hides the progress bar
func (m *Manager) HideProgressBar() {
	if m.progressBar != nil {
		m.progressBar.Hide()
	}
}

// ShowProgressBar shows the progress bar
func (m *Manager) ShowProgressBar() {
	if m.progressBar != nil {
		m.progressBar.Show()
	}
}

// SetWindowTitle sets the window title
func (m *Manager) SetWindowTitle(title string) {
	if m.window != nil {
		m.window.SetTitle(title)
	}
}

// GetCurrentStatus returns the current update status
func (m *Manager) GetCurrentStatus() UpdateStatus {
	return m.currentStatus
}

// IsWindowVisible returns whether the window is currently visible
func (m *Manager) IsWindowVisible() bool {
	return m.window != nil && m.window.Content() != nil
}

// RefreshUI refreshes the user interface
func (m *Manager) RefreshUI() {
	if m.window != nil && m.window.Content() != nil {
		m.window.Content().Refresh()
	}
}

// Close closes the application
func (m *Manager) Close() {
	if m.window != nil {
		m.window.Close()
	}
}