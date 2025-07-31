package install

import (
	"archive/zip"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"syscall"
)

// ChangesInfo 表示 changes.json 文件的结构
type ChangesInfo struct {
	Deleted  []string `json:"deleted"`
	Added    []string `json:"added"`
	Modified []string `json:"modified"`
}

// InstallManager 定义安装操作的接口契约
type InstallManager interface {
	ExtractZip(zipPath, destPath string) error
	ProcessChanges(changesPath string) (*ChangesInfo, error)
	ApplyUpdate(sourcePath, targetPath string, changes *ChangesInfo) error
	HandleRunningProcess(processName string) error
	CreateTempDir() (string, error)
	CleanupTempDir(tempDir string) error
}

// Manager 实现 InstallManager 接口
type Manager struct {
	tempDirs []string // 跟踪临时目录以便清理
}

// NewManager 创建新的安装管理器实例
func NewManager() *Manager {
	return &Manager{
		tempDirs: make([]string, 0),
	}
}

// CreateTempDir 为解压创建临时目录
func (m *Manager) CreateTempDir() (string, error) {
	tempDir, err := os.MkdirTemp("", "updater_*")
	if err != nil {
		return "", fmt.Errorf("创建临时目录失败: %w", err)
	}

	// 跟踪临时目录以便清理
	m.tempDirs = append(m.tempDirs, tempDir)
	return tempDir, nil
}

// CleanupTempDir 删除临时目录及其内容
func (m *Manager) CleanupTempDir(tempDir string) error {
	if tempDir == "" {
		return nil
	}

	err := os.RemoveAll(tempDir)
	if err != nil {
		return fmt.Errorf("清理临时目录 %s 失败: %w", tempDir, err)
	}

	// 从跟踪列表中删除
	for i, dir := range m.tempDirs {
		if dir == tempDir {
			m.tempDirs = append(m.tempDirs[:i], m.tempDirs[i+1:]...)
			break
		}
	}

	return nil
}

// CleanupAllTempDirs 删除所有跟踪的临时目录
func (m *Manager) CleanupAllTempDirs() error {
	var errors []string

	for _, tempDir := range m.tempDirs {
		if err := os.RemoveAll(tempDir); err != nil {
			errors = append(errors, fmt.Sprintf("清理 %s 失败: %v", tempDir, err))
		}
	}

	m.tempDirs = m.tempDirs[:0] // 清空切片

	if len(errors) > 0 {
		return fmt.Errorf("清理错误: %s", strings.Join(errors, "; "))
	}

	return nil
}

// ExtractZip 将 ZIP 文件解压到指定的目标目录
func (m *Manager) ExtractZip(zipPath, destPath string) error {
	// 打开 ZIP 文件进行读取
	reader, err := zip.OpenReader(zipPath)
	if err != nil {
		return fmt.Errorf("打开 ZIP 文件 %s 失败: %w", zipPath, err)
	}
	defer reader.Close()

	// 如果目标目录不存在则创建
	if err := os.MkdirAll(destPath, 0755); err != nil {
		return fmt.Errorf("创建目标目录 %s 失败: %w", destPath, err)
	}

	// 解压文件
	for _, file := range reader.File {
		if err := m.extractFile(file, destPath); err != nil {
			return fmt.Errorf("解压文件 %s 失败: %w", file.Name, err)
		}
	}

	return nil
}

// extractFile 从 ZIP 归档中解压单个文件
func (m *Manager) extractFile(file *zip.File, destPath string) error {
	// 清理文件路径以防止目录遍历攻击
	cleanPath := filepath.Clean(file.Name)
	if strings.Contains(cleanPath, "..") {
		return fmt.Errorf("无效的文件路径: %s", file.Name)
	}

	// 创建完整的目标路径
	destFile := filepath.Join(destPath, cleanPath)

	// 如果需要则创建目录结构
	if file.FileInfo().IsDir() {
		return os.MkdirAll(destFile, file.FileInfo().Mode())
	}

	// 创建父目录
	if err := os.MkdirAll(filepath.Dir(destFile), 0755); err != nil {
		return fmt.Errorf("创建父目录失败: %w", err)
	}

	// 打开 ZIP 归档中的文件
	rc, err := file.Open()
	if err != nil {
		return fmt.Errorf("打开归档中的文件失败: %w", err)
	}
	defer rc.Close()

	// 创建目标文件
	outFile, err := os.OpenFile(destFile, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, file.FileInfo().Mode())
	if err != nil {
		return fmt.Errorf("创建目标文件失败: %w", err)
	}
	defer outFile.Close()

	// 复制文件内容
	_, err = io.Copy(outFile, rc)
	if err != nil {
		return fmt.Errorf("复制文件内容失败: %w", err)
	}

	return nil
}

// ProcessChanges 读取并解析 changes.json 文件
func (m *Manager) ProcessChanges(changesPath string) (*ChangesInfo, error) {
	// 检查 changes.json 是否存在
	if _, err := os.Stat(changesPath); os.IsNotExist(err) {
		// 如果 changes.json 不存在，返回空的变更信息
		return &ChangesInfo{
			Deleted:  []string{},
			Added:    []string{},
			Modified: []string{},
		}, nil
	}

	// 读取 changes.json 文件
	data, err := os.ReadFile(changesPath)
	if err != nil {
		return nil, fmt.Errorf("读取变更文件 %s 失败: %w", changesPath, err)
	}

	// 解析 JSON
	var changes ChangesInfo
	if err := json.Unmarshal(data, &changes); err != nil {
		return nil, fmt.Errorf("解析变更 JSON 失败: %w", err)
	}

	return &changes, nil
}

// HandleRunningProcess 通过重命名正在使用的文件来处理正在运行的进程
func (m *Manager) HandleRunningProcess(processName string) error {
	// 获取当前可执行文件路径
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("获取可执行文件路径失败: %w", err)
	}

	exeDir := filepath.Dir(exePath)
	targetFile := filepath.Join(exeDir, processName)

	// 检查目标文件是否存在
	if _, err := os.Stat(targetFile); os.IsNotExist(err) {
		// 文件不存在，无需处理
		return nil
	}

	// 尝试重命名文件以指示应在下次启动时删除
	oldFile := targetFile + ".old"

	// 如果存在现有的 .old 文件则删除
	if _, err := os.Stat(oldFile); err == nil {
		if err := os.Remove(oldFile); err != nil {
			return fmt.Errorf("删除现有旧文件 %s 失败: %w", oldFile, err)
		}
	}

	// 将当前文件重命名为 .old
	if err := os.Rename(targetFile, oldFile); err != nil {
		// 如果重命名失败，进程可能正在运行
		// 在 Windows 上，我们无法重命名正在运行的可执行文件
		if isFileInUse(err) {
			// 标记文件在下次重启时删除（Windows 特定）
			return m.markFileForDeletion(targetFile)
		}
		return fmt.Errorf("重命名正在运行的进程文件 %s 失败: %w", targetFile, err)
	}

	return nil
}

// isFileInUse 检查错误是否表示文件正在使用中
func isFileInUse(err error) bool {
	if err == nil {
		return false
	}

	// 检查 Windows 特定的"文件正在使用"错误
	if pathErr, ok := err.(*os.PathError); ok {
		if errno, ok := pathErr.Err.(syscall.Errno); ok {
			// ERROR_SHARING_VIOLATION (32) 或 ERROR_ACCESS_DENIED (5)
			return errno == syscall.Errno(32) || errno == syscall.Errno(5)
		}
	}

	return strings.Contains(err.Error(), "being used by another process") ||
		strings.Contains(err.Error(), "access is denied")
}

// markFileForDeletion 标记文件在下次系统重启时删除（Windows 特定）
func (m *Manager) markFileForDeletion(filePath string) error {
	// 这是 Windows 特定的实现
	// 目前，我们将创建一个可由主应用程序处理的标记文件
	markerFile := filePath + ".delete_on_restart"

	// 创建标记文件
	file, err := os.Create(markerFile)
	if err != nil {
		return fmt.Errorf("创建删除标记文件失败: %w", err)
	}
	defer file.Close()

	// 将目标文件路径写入标记文件
	_, err = file.WriteString(filePath)
	if err != nil {
		return fmt.Errorf("写入标记文件失败: %w", err)
	}

	return nil
}

// DeleteMarkedFiles 删除标记为删除的文件
func (m *Manager) DeleteMarkedFiles(directory string) error {
	// 查找所有 .delete_on_restart 文件
	pattern := filepath.Join(directory, "*.delete_on_restart")
	matches, err := filepath.Glob(pattern)
	if err != nil {
		return fmt.Errorf("查找标记文件失败: %w", err)
	}

	var errors []string
	for _, markerFile := range matches {
		// 读取目标文件路径
		data, err := os.ReadFile(markerFile)
		if err != nil {
			errors = append(errors, fmt.Sprintf("读取标记文件 %s 失败: %v", markerFile, err))
			continue
		}

		targetFile := strings.TrimSpace(string(data))

		// 尝试删除目标文件
		if err := os.Remove(targetFile); err != nil && !os.IsNotExist(err) {
			errors = append(errors, fmt.Sprintf("删除标记文件 %s 失败: %v", targetFile, err))
		}

		// 删除标记文件
		if err := os.Remove(markerFile); err != nil {
			errors = append(errors, fmt.Sprintf("删除标记文件 %s 失败: %v", markerFile, err))
		}
	}

	if len(errors) > 0 {
		return fmt.Errorf("删除错误: %s", strings.Join(errors, "; "))
	}

	return nil
}

// ApplyUpdate 通过从源目录复制文件到目标目录来应用更新
func (m *Manager) ApplyUpdate(sourcePath, targetPath string, changes *ChangesInfo) error {
	// 创建备份目录
	backupDir, err := m.createBackupDir(targetPath)
	if err != nil {
		return fmt.Errorf("创建备份目录失败: %w", err)
	}

	// 在应用更新前备份现有文件
	if err := m.backupFiles(targetPath, backupDir, changes); err != nil {
		return fmt.Errorf("备份文件失败: %w", err)
	}

	// 应用更新
	if err := m.applyUpdateFiles(sourcePath, targetPath, changes); err != nil {
		// 失败时回滚
		if rollbackErr := m.rollbackUpdate(targetPath, backupDir); rollbackErr != nil {
			return fmt.Errorf("更新失败且回滚失败: 更新错误: %w, 回滚错误: %v", err, rollbackErr)
		}
		return fmt.Errorf("更新失败已回滚: %w", err)
	}

	// 成功更新后清理备份目录
	if err := os.RemoveAll(backupDir); err != nil {
		// 记录警告但不让更新失败
		fmt.Printf("警告: 清理备份目录 %s 失败: %v\n", backupDir, err)
	}

	return nil
}

// createBackupDir 为更新创建备份目录
func (m *Manager) createBackupDir(targetPath string) (string, error) {
	backupDir := filepath.Join(targetPath, ".backup_"+fmt.Sprintf("%d", os.Getpid()))

	if err := os.MkdirAll(backupDir, 0755); err != nil {
		return "", fmt.Errorf("创建备份目录失败: %w", err)
	}

	return backupDir, nil
}

// backupFiles 创建将被修改或删除的文件的备份
func (m *Manager) backupFiles(targetPath, backupDir string, changes *ChangesInfo) error {
	// 备份将被修改的文件
	for _, file := range changes.Modified {
		srcFile := filepath.Join(targetPath, file)
		if _, err := os.Stat(srcFile); os.IsNotExist(err) {
			continue // 文件不存在，跳过备份
		}

		backupFile := filepath.Join(backupDir, file)
		if err := m.copyFileWithDirs(srcFile, backupFile); err != nil {
			return fmt.Errorf("备份修改文件 %s 失败: %w", file, err)
		}
	}

	// 备份将被删除的文件
	for _, file := range changes.Deleted {
		srcFile := filepath.Join(targetPath, file)
		if _, err := os.Stat(srcFile); os.IsNotExist(err) {
			continue // 文件不存在，跳过备份
		}

		backupFile := filepath.Join(backupDir, file)
		if err := m.copyFileWithDirs(srcFile, backupFile); err != nil {
			return fmt.Errorf("备份删除文件 %s 失败: %w", file, err)
		}
	}

	return nil
}

// applyUpdateFiles 应用实际的文件更改
func (m *Manager) applyUpdateFiles(sourcePath, targetPath string, changes *ChangesInfo) error {
	// 删除标记为删除的文件
	for _, file := range changes.Deleted {
		targetFile := filepath.Join(targetPath, file)
		if err := os.Remove(targetFile); err != nil && !os.IsNotExist(err) {
			return fmt.Errorf("删除文件 %s 失败: %w", file, err)
		}
	}

	// 复制新文件和修改的文件
	filesToCopy := append(changes.Added, changes.Modified...)
	for _, file := range filesToCopy {
		srcFile := filepath.Join(sourcePath, file)
		targetFile := filepath.Join(targetPath, file)

		// 检查源文件是否存在
		if _, err := os.Stat(srcFile); os.IsNotExist(err) {
			continue // 源文件不存在，跳过
		}

		if err := m.copyFileWithDirs(srcFile, targetFile); err != nil {
			return fmt.Errorf("复制文件 %s 失败: %w", file, err)
		}
	}

	return nil
}

// copyFileWithDirs 复制文件并创建必要的目录
func (m *Manager) copyFileWithDirs(src, dst string) error {
	// 创建父目录
	if err := os.MkdirAll(filepath.Dir(dst), 0755); err != nil {
		return fmt.Errorf("创建父目录失败: %w", err)
	}

	// 打开源文件
	srcFile, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("打开源文件失败: %w", err)
	}
	defer srcFile.Close()

	// 获取源文件信息
	srcInfo, err := srcFile.Stat()
	if err != nil {
		return fmt.Errorf("获取源文件信息失败: %w", err)
	}

	// 创建目标文件
	dstFile, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, srcInfo.Mode())
	if err != nil {
		return fmt.Errorf("创建目标文件失败: %w", err)
	}
	defer dstFile.Close()

	// 复制文件内容
	_, err = io.Copy(dstFile, srcFile)
	if err != nil {
		return fmt.Errorf("复制文件内容失败: %w", err)
	}

	return nil
}

// rollbackUpdate 在更新失败时从备份恢复文件
func (m *Manager) rollbackUpdate(targetPath, backupDir string) error {
	// 遍历备份目录并恢复文件
	return filepath.Walk(backupDir, func(backupFile string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		if info.IsDir() {
			return nil // 跳过目录
		}

		// 计算相对路径
		relPath, err := filepath.Rel(backupDir, backupFile)
		if err != nil {
			return fmt.Errorf("计算相对路径失败: %w", err)
		}

		// 将文件恢复到目标位置
		targetFile := filepath.Join(targetPath, relPath)
		if err := m.copyFileWithDirs(backupFile, targetFile); err != nil {
			return fmt.Errorf("恢复文件 %s 失败: %w", relPath, err)
		}

		return nil
	})
}
