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

// ChangesInfo represents the structure of changes.json file
type ChangesInfo struct {
	Deleted  []string `json:"deleted"`
	Added    []string `json:"added"`
	Modified []string `json:"modified"`
}

// InstallManager interface defines the contract for installation operations
type InstallManager interface {
	ExtractZip(zipPath, destPath string) error
	ProcessChanges(changesPath string) (*ChangesInfo, error)
	ApplyUpdate(sourcePath, targetPath string, changes *ChangesInfo) error
	HandleRunningProcess(processName string) error
	CreateTempDir() (string, error)
	CleanupTempDir(tempDir string) error
}

// Manager implements the InstallManager interface
type Manager struct {
	tempDirs []string // Track temporary directories for cleanup
}

// NewManager creates a new install manager instance
func NewManager() *Manager {
	return &Manager{
		tempDirs: make([]string, 0),
	}
}

// CreateTempDir creates a temporary directory for extraction
func (m *Manager) CreateTempDir() (string, error) {
	tempDir, err := os.MkdirTemp("", "updater_*")
	if err != nil {
		return "", fmt.Errorf("failed to create temp directory: %w", err)
	}

	// Track temp directory for cleanup
	m.tempDirs = append(m.tempDirs, tempDir)
	return tempDir, nil
}

// CleanupTempDir removes a temporary directory and its contents
func (m *Manager) CleanupTempDir(tempDir string) error {
	if tempDir == "" {
		return nil
	}

	err := os.RemoveAll(tempDir)
	if err != nil {
		return fmt.Errorf("failed to cleanup temp directory %s: %w", tempDir, err)
	}

	// Remove from tracking list
	for i, dir := range m.tempDirs {
		if dir == tempDir {
			m.tempDirs = append(m.tempDirs[:i], m.tempDirs[i+1:]...)
			break
		}
	}

	return nil
}

// CleanupAllTempDirs removes all tracked temporary directories
func (m *Manager) CleanupAllTempDirs() error {
	var errors []string

	for _, tempDir := range m.tempDirs {
		if err := os.RemoveAll(tempDir); err != nil {
			errors = append(errors, fmt.Sprintf("failed to cleanup %s: %v", tempDir, err))
		}
	}

	m.tempDirs = m.tempDirs[:0] // Clear the slice

	if len(errors) > 0 {
		return fmt.Errorf("cleanup errors: %s", strings.Join(errors, "; "))
	}

	return nil
}

// ExtractZip extracts a ZIP file to the specified destination directory
func (m *Manager) ExtractZip(zipPath, destPath string) error {
	// Open ZIP file for reading
	reader, err := zip.OpenReader(zipPath)
	if err != nil {
		return fmt.Errorf("failed to open ZIP file %s: %w", zipPath, err)
	}
	defer reader.Close()

	// Create destination directory if it doesn't exist
	if err := os.MkdirAll(destPath, 0755); err != nil {
		return fmt.Errorf("failed to create destination directory %s: %w", destPath, err)
	}

	// Extract files
	for _, file := range reader.File {
		if err := m.extractFile(file, destPath); err != nil {
			return fmt.Errorf("failed to extract file %s: %w", file.Name, err)
		}
	}

	return nil
}

// extractFile extracts a single file from the ZIP archive
func (m *Manager) extractFile(file *zip.File, destPath string) error {
	// Clean the file path to prevent directory traversal attacks
	cleanPath := filepath.Clean(file.Name)
	if strings.Contains(cleanPath, "..") {
		return fmt.Errorf("invalid file path: %s", file.Name)
	}

	// Create full destination path
	destFile := filepath.Join(destPath, cleanPath)

	// Create directory structure if needed
	if file.FileInfo().IsDir() {
		return os.MkdirAll(destFile, file.FileInfo().Mode())
	}

	// Create parent directories
	if err := os.MkdirAll(filepath.Dir(destFile), 0755); err != nil {
		return fmt.Errorf("failed to create parent directory: %w", err)
	}

	// Open file in ZIP archive
	rc, err := file.Open()
	if err != nil {
		return fmt.Errorf("failed to open file in archive: %w", err)
	}
	defer rc.Close()

	// Create destination file
	outFile, err := os.OpenFile(destFile, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, file.FileInfo().Mode())
	if err != nil {
		return fmt.Errorf("failed to create destination file: %w", err)
	}
	defer outFile.Close()

	// Copy file contents
	_, err = io.Copy(outFile, rc)
	if err != nil {
		return fmt.Errorf("failed to copy file contents: %w", err)
	}

	return nil
}

// ProcessChanges reads and parses the changes.json file
func (m *Manager) ProcessChanges(changesPath string) (*ChangesInfo, error) {
	// Check if changes.json exists
	if _, err := os.Stat(changesPath); os.IsNotExist(err) {
		// If changes.json doesn't exist, return empty changes info
		return &ChangesInfo{
			Deleted:  []string{},
			Added:    []string{},
			Modified: []string{},
		}, nil
	}

	// Read the changes.json file
	data, err := os.ReadFile(changesPath)
	if err != nil {
		return nil, fmt.Errorf("failed to read changes file %s: %w", changesPath, err)
	}

	// Parse JSON
	var changes ChangesInfo
	if err := json.Unmarshal(data, &changes); err != nil {
		return nil, fmt.Errorf("failed to parse changes JSON: %w", err)
	}

	return &changes, nil
}

// HandleRunningProcess handles running processes by renaming files that are in use
func (m *Manager) HandleRunningProcess(processName string) error {
	// Get the current executable path
	exePath, err := os.Executable()
	if err != nil {
		return fmt.Errorf("failed to get executable path: %w", err)
	}

	exeDir := filepath.Dir(exePath)
	targetFile := filepath.Join(exeDir, processName)

	// Check if the target file exists
	if _, err := os.Stat(targetFile); os.IsNotExist(err) {
		// File doesn't exist, nothing to handle
		return nil
	}

	// Try to rename the file to indicate it should be deleted on next startup
	oldFile := targetFile + ".old"

	// Remove existing .old file if it exists
	if _, err := os.Stat(oldFile); err == nil {
		if err := os.Remove(oldFile); err != nil {
			return fmt.Errorf("failed to remove existing old file %s: %w", oldFile, err)
		}
	}

	// Rename the current file to .old
	if err := os.Rename(targetFile, oldFile); err != nil {
		// If rename fails, the process might be running
		// On Windows, we can't rename a running executable
		if isFileInUse(err) {
			// Mark the file for deletion on next reboot (Windows specific)
			return m.markFileForDeletion(targetFile)
		}
		return fmt.Errorf("failed to rename running process file %s: %w", targetFile, err)
	}

	return nil
}

// isFileInUse checks if the error indicates the file is in use
func isFileInUse(err error) bool {
	if err == nil {
		return false
	}

	// Check for Windows-specific "file in use" errors
	if pathErr, ok := err.(*os.PathError); ok {
		if errno, ok := pathErr.Err.(syscall.Errno); ok {
			// ERROR_SHARING_VIOLATION (32) or ERROR_ACCESS_DENIED (5)
			return errno == syscall.Errno(32) || errno == syscall.Errno(5)
		}
	}

	return strings.Contains(err.Error(), "being used by another process") ||
		strings.Contains(err.Error(), "access is denied")
}

// markFileForDeletion marks a file for deletion on next system reboot (Windows specific)
func (m *Manager) markFileForDeletion(filePath string) error {
	// This is a Windows-specific implementation
	// For now, we'll create a marker file that can be handled by the main application
	markerFile := filePath + ".delete_on_restart"

	// Create a marker file
	file, err := os.Create(markerFile)
	if err != nil {
		return fmt.Errorf("failed to create deletion marker file: %w", err)
	}
	defer file.Close()

	// Write the target file path to the marker
	_, err = file.WriteString(filePath)
	if err != nil {
		return fmt.Errorf("failed to write to marker file: %w", err)
	}

	return nil
}

// DeleteMarkedFiles removes files that were marked for deletion
func (m *Manager) DeleteMarkedFiles(directory string) error {
	// Find all .delete_on_restart files
	pattern := filepath.Join(directory, "*.delete_on_restart")
	matches, err := filepath.Glob(pattern)
	if err != nil {
		return fmt.Errorf("failed to find marker files: %w", err)
	}

	var errors []string
	for _, markerFile := range matches {
		// Read the target file path
		data, err := os.ReadFile(markerFile)
		if err != nil {
			errors = append(errors, fmt.Sprintf("failed to read marker file %s: %v", markerFile, err))
			continue
		}

		targetFile := strings.TrimSpace(string(data))

		// Try to delete the target file
		if err := os.Remove(targetFile); err != nil && !os.IsNotExist(err) {
			errors = append(errors, fmt.Sprintf("failed to delete marked file %s: %v", targetFile, err))
		}

		// Remove the marker file
		if err := os.Remove(markerFile); err != nil {
			errors = append(errors, fmt.Sprintf("failed to remove marker file %s: %v", markerFile, err))
		}
	}

	if len(errors) > 0 {
		return fmt.Errorf("deletion errors: %s", strings.Join(errors, "; "))
	}

	return nil
}

// ApplyUpdate applies the update by copying files from source to target directory
func (m *Manager) ApplyUpdate(sourcePath, targetPath string, changes *ChangesInfo) error {
	// Create backup directory
	backupDir, err := m.createBackupDir(targetPath)
	if err != nil {
		return fmt.Errorf("failed to create backup directory: %w", err)
	}

	// Backup existing files before applying update
	if err := m.backupFiles(targetPath, backupDir, changes); err != nil {
		return fmt.Errorf("failed to backup files: %w", err)
	}

	// Apply the update
	if err := m.applyUpdateFiles(sourcePath, targetPath, changes); err != nil {
		// Rollback on failure
		if rollbackErr := m.rollbackUpdate(targetPath, backupDir); rollbackErr != nil {
			return fmt.Errorf("update failed and rollback failed: update error: %w, rollback error: %v", err, rollbackErr)
		}
		return fmt.Errorf("update failed and was rolled back: %w", err)
	}

	// Clean up backup directory after successful update
	if err := os.RemoveAll(backupDir); err != nil {
		// Log warning but don't fail the update
		fmt.Printf("Warning: failed to cleanup backup directory %s: %v\n", backupDir, err)
	}

	return nil
}

// createBackupDir creates a backup directory for the update
func (m *Manager) createBackupDir(targetPath string) (string, error) {
	backupDir := filepath.Join(targetPath, ".backup_"+fmt.Sprintf("%d", os.Getpid()))

	if err := os.MkdirAll(backupDir, 0755); err != nil {
		return "", fmt.Errorf("failed to create backup directory: %w", err)
	}

	return backupDir, nil
}

// backupFiles creates backups of files that will be modified or deleted
func (m *Manager) backupFiles(targetPath, backupDir string, changes *ChangesInfo) error {
	// Backup files that will be modified
	for _, file := range changes.Modified {
		srcFile := filepath.Join(targetPath, file)
		if _, err := os.Stat(srcFile); os.IsNotExist(err) {
			continue // File doesn't exist, skip backup
		}

		backupFile := filepath.Join(backupDir, file)
		if err := m.copyFileWithDirs(srcFile, backupFile); err != nil {
			return fmt.Errorf("failed to backup modified file %s: %w", file, err)
		}
	}

	// Backup files that will be deleted
	for _, file := range changes.Deleted {
		srcFile := filepath.Join(targetPath, file)
		if _, err := os.Stat(srcFile); os.IsNotExist(err) {
			continue // File doesn't exist, skip backup
		}

		backupFile := filepath.Join(backupDir, file)
		if err := m.copyFileWithDirs(srcFile, backupFile); err != nil {
			return fmt.Errorf("failed to backup deleted file %s: %w", file, err)
		}
	}

	return nil
}

// applyUpdateFiles applies the actual file changes
func (m *Manager) applyUpdateFiles(sourcePath, targetPath string, changes *ChangesInfo) error {
	// Delete files marked for deletion
	for _, file := range changes.Deleted {
		targetFile := filepath.Join(targetPath, file)
		if err := os.Remove(targetFile); err != nil && !os.IsNotExist(err) {
			return fmt.Errorf("failed to delete file %s: %w", file, err)
		}
	}

	// Copy new and modified files
	filesToCopy := append(changes.Added, changes.Modified...)
	for _, file := range filesToCopy {
		srcFile := filepath.Join(sourcePath, file)
		targetFile := filepath.Join(targetPath, file)

		// Check if source file exists
		if _, err := os.Stat(srcFile); os.IsNotExist(err) {
			continue // Source file doesn't exist, skip
		}

		if err := m.copyFileWithDirs(srcFile, targetFile); err != nil {
			return fmt.Errorf("failed to copy file %s: %w", file, err)
		}
	}

	return nil
}

// copyFileWithDirs copies a file and creates necessary directories
func (m *Manager) copyFileWithDirs(src, dst string) error {
	// Create parent directories
	if err := os.MkdirAll(filepath.Dir(dst), 0755); err != nil {
		return fmt.Errorf("failed to create parent directories: %w", err)
	}

	// Open source file
	srcFile, err := os.Open(src)
	if err != nil {
		return fmt.Errorf("failed to open source file: %w", err)
	}
	defer srcFile.Close()

	// Get source file info
	srcInfo, err := srcFile.Stat()
	if err != nil {
		return fmt.Errorf("failed to get source file info: %w", err)
	}

	// Create destination file
	dstFile, err := os.OpenFile(dst, os.O_WRONLY|os.O_CREATE|os.O_TRUNC, srcInfo.Mode())
	if err != nil {
		return fmt.Errorf("failed to create destination file: %w", err)
	}
	defer dstFile.Close()

	// Copy file contents
	_, err = io.Copy(dstFile, srcFile)
	if err != nil {
		return fmt.Errorf("failed to copy file contents: %w", err)
	}

	return nil
}

// rollbackUpdate restores files from backup in case of update failure
func (m *Manager) rollbackUpdate(targetPath, backupDir string) error {
	// Walk through backup directory and restore files
	return filepath.Walk(backupDir, func(backupFile string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}

		if info.IsDir() {
			return nil // Skip directories
		}

		// Calculate relative path
		relPath, err := filepath.Rel(backupDir, backupFile)
		if err != nil {
			return fmt.Errorf("failed to calculate relative path: %w", err)
		}

		// Restore file to target location
		targetFile := filepath.Join(targetPath, relPath)
		if err := m.copyFileWithDirs(backupFile, targetFile); err != nil {
			return fmt.Errorf("failed to restore file %s: %w", relPath, err)
		}

		return nil
	})
}
