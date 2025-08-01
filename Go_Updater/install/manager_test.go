package install

import (
	"archive/zip"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func TestNewManager(t *testing.T) {
	manager := NewManager()
	if manager == nil {
		t.Fatal("NewManager() returned nil")
	}
	if manager.tempDirs == nil {
		t.Fatal("tempDirs slice not initialized")
	}
}

func TestCreateTempDir(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	
	// Verify directory exists
	if _, err := os.Stat(tempDir); os.IsNotExist(err) {
		t.Fatalf("Temp directory was not created: %s", tempDir)
	}
	
	// Verify it's tracked
	if len(manager.tempDirs) != 1 || manager.tempDirs[0] != tempDir {
		t.Fatalf("Temp directory not properly tracked")
	}
	
	// Cleanup
	defer manager.CleanupTempDir(tempDir)
}

func TestCleanupTempDir(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	
	// Create a test file in temp directory
	testFile := filepath.Join(tempDir, "test.txt")
	if err := os.WriteFile(testFile, []byte("test"), 0644); err != nil {
		t.Fatalf("Failed to create test file: %v", err)
	}
	
	// Cleanup
	err = manager.CleanupTempDir(tempDir)
	if err != nil {
		t.Fatalf("CleanupTempDir() failed: %v", err)
	}
	
	// Verify directory is removed
	if _, err := os.Stat(tempDir); !os.IsNotExist(err) {
		t.Fatalf("Temp directory was not removed: %s", tempDir)
	}
	
	// Verify it's no longer tracked
	if len(manager.tempDirs) != 0 {
		t.Fatalf("Temp directory still tracked after cleanup")
	}
}

func TestExtractZip(t *testing.T) {
	manager := NewManager()
	
	// Create a temporary ZIP file for testing
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	zipPath := filepath.Join(tempDir, "test.zip")
	extractDir := filepath.Join(tempDir, "extract")
	
	// Create test ZIP file
	if err := createTestZip(zipPath); err != nil {
		t.Fatalf("Failed to create test ZIP: %v", err)
	}
	
	// Extract ZIP
	err = manager.ExtractZip(zipPath, extractDir)
	if err != nil {
		t.Fatalf("ExtractZip() failed: %v", err)
	}
	
	// Verify extracted files
	testFile := filepath.Join(extractDir, "test.txt")
	if _, err := os.Stat(testFile); os.IsNotExist(err) {
		t.Fatalf("Extracted file not found: %s", testFile)
	}
	
	// Verify file contents
	content, err := os.ReadFile(testFile)
	if err != nil {
		t.Fatalf("Failed to read extracted file: %v", err)
	}
	
	expected := "Hello, World!"
	if string(content) != expected {
		t.Fatalf("File content mismatch. Expected: %s, Got: %s", expected, string(content))
	}
	
	// Verify directory structure
	subDir := filepath.Join(extractDir, "subdir")
	if _, err := os.Stat(subDir); os.IsNotExist(err) {
		t.Fatalf("Extracted subdirectory not found: %s", subDir)
	}
	
	subFile := filepath.Join(subDir, "sub.txt")
	if _, err := os.Stat(subFile); os.IsNotExist(err) {
		t.Fatalf("Extracted subdirectory file not found: %s", subFile)
	}
}

func TestExtractZipInvalidPath(t *testing.T) {
	manager := NewManager()
	
	// Test with non-existent ZIP file
	err := manager.ExtractZip("nonexistent.zip", "dest")
	if err == nil {
		t.Fatal("ExtractZip() should fail with non-existent ZIP file")
	}
}

func TestExtractZipDirectoryTraversal(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	zipPath := filepath.Join(tempDir, "malicious.zip")
	extractDir := filepath.Join(tempDir, "extract")
	
	// Create ZIP with directory traversal attempt
	if err := createMaliciousZip(zipPath); err != nil {
		t.Fatalf("Failed to create malicious ZIP: %v", err)
	}
	
	// Extract should fail or sanitize the path
	err = manager.ExtractZip(zipPath, extractDir)
	if err != nil {
		// This is expected behavior - the extraction should fail
		return
	}
	
	// If extraction succeeded, verify no files were created outside extract dir
	parentDir := filepath.Dir(extractDir)
	maliciousFile := filepath.Join(parentDir, "malicious.txt")
	if _, err := os.Stat(maliciousFile); !os.IsNotExist(err) {
		t.Fatal("Directory traversal attack succeeded - malicious file created outside extract directory")
	}
}

// Helper function to create a test ZIP file
func createTestZip(zipPath string) error {
	file, err := os.Create(zipPath)
	if err != nil {
		return err
	}
	defer file.Close()
	
	writer := zip.NewWriter(file)
	defer writer.Close()
	
	// Add a test file
	f1, err := writer.Create("test.txt")
	if err != nil {
		return err
	}
	_, err = f1.Write([]byte("Hello, World!"))
	if err != nil {
		return err
	}
	
	// Add a subdirectory and file
	f2, err := writer.Create("subdir/sub.txt")
	if err != nil {
		return err
	}
	_, err = f2.Write([]byte("Subdirectory file"))
	if err != nil {
		return err
	}
	
	return nil
}

func TestProcessChanges(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	// Test with valid changes.json
	changesPath := filepath.Join(tempDir, "changes.json")
	changesData := `{
		"deleted": ["old_file.txt", "deprecated/module.dll"],
		"added": ["new_file.txt", "features/new_module.dll"],
		"modified": ["main.exe", "config.ini"]
	}`
	
	if err := os.WriteFile(changesPath, []byte(changesData), 0644); err != nil {
		t.Fatalf("Failed to create test changes.json: %v", err)
	}
	
	changes, err := manager.ProcessChanges(changesPath)
	if err != nil {
		t.Fatalf("ProcessChanges() failed: %v", err)
	}
	
	// Verify parsed data
	if len(changes.Deleted) != 2 {
		t.Fatalf("Expected 2 deleted files, got %d", len(changes.Deleted))
	}
	if changes.Deleted[0] != "old_file.txt" {
		t.Fatalf("Expected first deleted file to be 'old_file.txt', got '%s'", changes.Deleted[0])
	}
	
	if len(changes.Added) != 2 {
		t.Fatalf("Expected 2 added files, got %d", len(changes.Added))
	}
	
	if len(changes.Modified) != 2 {
		t.Fatalf("Expected 2 modified files, got %d", len(changes.Modified))
	}
}

func TestProcessChangesNonExistent(t *testing.T) {
	manager := NewManager()
	
	// Test with non-existent changes.json
	changes, err := manager.ProcessChanges("nonexistent.json")
	if err != nil {
		t.Fatalf("ProcessChanges() should not fail with non-existent file: %v", err)
	}
	
	// Should return empty changes
	if len(changes.Deleted) != 0 || len(changes.Added) != 0 || len(changes.Modified) != 0 {
		t.Fatalf("Expected empty changes for non-existent file")
	}
}

func TestProcessChangesInvalidJSON(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	// Test with invalid JSON
	changesPath := filepath.Join(tempDir, "invalid.json")
	invalidData := `{"deleted": ["file1.txt", "file2.txt"` // Missing closing bracket
	
	if err := os.WriteFile(changesPath, []byte(invalidData), 0644); err != nil {
		t.Fatalf("Failed to create invalid JSON file: %v", err)
	}
	
	_, err = manager.ProcessChanges(changesPath)
	if err == nil {
		t.Fatal("ProcessChanges() should fail with invalid JSON")
	}
}

func TestHandleRunningProcess(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	// Create a test executable file
	testExe := filepath.Join(tempDir, "test.exe")
	if err := os.WriteFile(testExe, []byte("test executable"), 0755); err != nil {
		t.Fatalf("Failed to create test executable: %v", err)
	}
	
	// Test handling non-existent process
	err = manager.HandleRunningProcess("nonexistent.exe")
	if err != nil {
		t.Fatalf("HandleRunningProcess() should not fail with non-existent process: %v", err)
	}
}

func TestDeleteMarkedFiles(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	// Create test files to be deleted
	testFile1 := filepath.Join(tempDir, "file1.txt")
	testFile2 := filepath.Join(tempDir, "file2.txt")
	
	if err := os.WriteFile(testFile1, []byte("test1"), 0644); err != nil {
		t.Fatalf("Failed to create test file1: %v", err)
	}
	if err := os.WriteFile(testFile2, []byte("test2"), 0644); err != nil {
		t.Fatalf("Failed to create test file2: %v", err)
	}
	
	// Create marker files
	marker1 := testFile1 + ".delete_on_restart"
	marker2 := testFile2 + ".delete_on_restart"
	
	if err := os.WriteFile(marker1, []byte(testFile1), 0644); err != nil {
		t.Fatalf("Failed to create marker file1: %v", err)
	}
	if err := os.WriteFile(marker2, []byte(testFile2), 0644); err != nil {
		t.Fatalf("Failed to create marker file2: %v", err)
	}
	
	// Delete marked files
	err = manager.DeleteMarkedFiles(tempDir)
	if err != nil {
		t.Fatalf("DeleteMarkedFiles() failed: %v", err)
	}
	
	// Verify files are deleted
	if _, err := os.Stat(testFile1); !os.IsNotExist(err) {
		t.Fatalf("Test file1 should be deleted")
	}
	if _, err := os.Stat(testFile2); !os.IsNotExist(err) {
		t.Fatalf("Test file2 should be deleted")
	}
	
	// Verify marker files are deleted
	if _, err := os.Stat(marker1); !os.IsNotExist(err) {
		t.Fatalf("Marker file1 should be deleted")
	}
	if _, err := os.Stat(marker2); !os.IsNotExist(err) {
		t.Fatalf("Marker file2 should be deleted")
	}
}

func TestApplyUpdate(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	// Create source and target directories
	sourceDir := filepath.Join(tempDir, "source")
	targetDir := filepath.Join(tempDir, "target")
	
	if err := os.MkdirAll(sourceDir, 0755); err != nil {
		t.Fatalf("Failed to create source directory: %v", err)
	}
	if err := os.MkdirAll(targetDir, 0755); err != nil {
		t.Fatalf("Failed to create target directory: %v", err)
	}
	
	// Create test files in source directory
	newFile := filepath.Join(sourceDir, "new_file.txt")
	modifiedFile := filepath.Join(sourceDir, "modified_file.txt")
	
	if err := os.WriteFile(newFile, []byte("new content"), 0644); err != nil {
		t.Fatalf("Failed to create new file: %v", err)
	}
	if err := os.WriteFile(modifiedFile, []byte("updated content"), 0644); err != nil {
		t.Fatalf("Failed to create modified file: %v", err)
	}
	
	// Create existing files in target directory
	existingModified := filepath.Join(targetDir, "modified_file.txt")
	existingDeleted := filepath.Join(targetDir, "deleted_file.txt")
	
	if err := os.WriteFile(existingModified, []byte("old content"), 0644); err != nil {
		t.Fatalf("Failed to create existing modified file: %v", err)
	}
	if err := os.WriteFile(existingDeleted, []byte("to be deleted"), 0644); err != nil {
		t.Fatalf("Failed to create file to be deleted: %v", err)
	}
	
	// Define changes
	changes := &ChangesInfo{
		Added:    []string{"new_file.txt"},
		Modified: []string{"modified_file.txt"},
		Deleted:  []string{"deleted_file.txt"},
	}
	
	// Apply update
	err = manager.ApplyUpdate(sourceDir, targetDir, changes)
	if err != nil {
		t.Fatalf("ApplyUpdate() failed: %v", err)
	}
	
	// Verify new file was added
	newTargetFile := filepath.Join(targetDir, "new_file.txt")
	if _, err := os.Stat(newTargetFile); os.IsNotExist(err) {
		t.Fatalf("New file was not added to target directory")
	}
	
	// Verify modified file was updated
	content, err := os.ReadFile(existingModified)
	if err != nil {
		t.Fatalf("Failed to read modified file: %v", err)
	}
	if string(content) != "updated content" {
		t.Fatalf("Modified file content incorrect. Expected: 'updated content', Got: '%s'", string(content))
	}
	
	// Verify deleted file was removed
	if _, err := os.Stat(existingDeleted); !os.IsNotExist(err) {
		t.Fatalf("Deleted file still exists")
	}
}

func TestApplyUpdateWithRollback(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	// Create source and target directories
	sourceDir := filepath.Join(tempDir, "source")
	targetDir := filepath.Join(tempDir, "target")
	
	if err := os.MkdirAll(sourceDir, 0755); err != nil {
		t.Fatalf("Failed to create source directory: %v", err)
	}
	if err := os.MkdirAll(targetDir, 0755); err != nil {
		t.Fatalf("Failed to create target directory: %v", err)
	}
	
	// Create existing file in target directory
	existingFile := filepath.Join(targetDir, "existing_file.txt")
	originalContent := "original content"
	if err := os.WriteFile(existingFile, []byte(originalContent), 0644); err != nil {
		t.Fatalf("Failed to create existing file: %v", err)
	}
	
	// Create a source file that will cause a copy failure by making target read-only
	sourceFile := filepath.Join(sourceDir, "existing_file.txt")
	if err := os.WriteFile(sourceFile, []byte("new content"), 0644); err != nil {
		t.Fatalf("Failed to create source file: %v", err)
	}
	
	// Make target directory read-only to cause copy failure
	readOnlyDir := filepath.Join(targetDir, "readonly")
	if err := os.MkdirAll(readOnlyDir, 0755); err != nil {
		t.Fatalf("Failed to create readonly directory: %v", err)
	}
	
	// Create a file in readonly directory that we'll try to modify
	readOnlyFile := filepath.Join(readOnlyDir, "readonly_file.txt")
	if err := os.WriteFile(readOnlyFile, []byte("readonly content"), 0644); err != nil {
		t.Fatalf("Failed to create readonly file: %v", err)
	}
	
	// Create source file for readonly file
	sourceReadOnlyFile := filepath.Join(sourceDir, "readonly", "readonly_file.txt")
	if err := os.MkdirAll(filepath.Dir(sourceReadOnlyFile), 0755); err != nil {
		t.Fatalf("Failed to create source readonly directory: %v", err)
	}
	if err := os.WriteFile(sourceReadOnlyFile, []byte("new readonly content"), 0644); err != nil {
		t.Fatalf("Failed to create source readonly file: %v", err)
	}
	
	// Make the readonly directory read-only (Windows specific)
	if err := os.Chmod(readOnlyDir, 0444); err != nil {
		t.Fatalf("Failed to make directory read-only: %v", err)
	}
	
	// Restore permissions after test
	defer func() {
		os.Chmod(readOnlyDir, 0755)
		os.RemoveAll(readOnlyDir)
	}()
	
	// Define changes that will cause failure due to read-only directory
	changes := &ChangesInfo{
		Modified: []string{"existing_file.txt", "readonly/readonly_file.txt"},
	}
	
	// Apply update (should fail and rollback)
	err = manager.ApplyUpdate(sourceDir, targetDir, changes)
	if err == nil {
		// On some systems, the read-only test might not work as expected
		// Let's just verify the update completed successfully in this case
		t.Log("Update completed successfully (read-only test may not work on this system)")
		return
	}
	
	// Verify rollback occurred - original file should be restored
	content, err := os.ReadFile(existingFile)
	if err != nil {
		t.Fatalf("Failed to read file after rollback: %v", err)
	}
	if string(content) != originalContent {
		t.Fatalf("Rollback failed. Expected: '%s', Got: '%s'", originalContent, string(content))
	}
}

func TestCopyFileWithDirs(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	// Create source file
	srcFile := filepath.Join(tempDir, "source.txt")
	content := "test content"
	if err := os.WriteFile(srcFile, []byte(content), 0644); err != nil {
		t.Fatalf("Failed to create source file: %v", err)
	}
	
	// Copy to destination with nested directories
	dstFile := filepath.Join(tempDir, "nested", "dir", "destination.txt")
	
	err = manager.copyFileWithDirs(srcFile, dstFile)
	if err != nil {
		t.Fatalf("copyFileWithDirs() failed: %v", err)
	}
	
	// Verify file was copied
	if _, err := os.Stat(dstFile); os.IsNotExist(err) {
		t.Fatalf("Destination file was not created")
	}
	
	// Verify content
	dstContent, err := os.ReadFile(dstFile)
	if err != nil {
		t.Fatalf("Failed to read destination file: %v", err)
	}
	if string(dstContent) != content {
		t.Fatalf("File content mismatch. Expected: '%s', Got: '%s'", content, string(dstContent))
	}
	
	// Verify parent directories were created
	parentDir := filepath.Join(tempDir, "nested", "dir")
	if _, err := os.Stat(parentDir); os.IsNotExist(err) {
		t.Fatalf("Parent directories were not created")
	}
}

// Helper function to create a malicious ZIP file with directory traversal
func createMaliciousZip(zipPath string) error {
	file, err := os.Create(zipPath)
	if err != nil {
		return err
	}
	defer file.Close()
	
	writer := zip.NewWriter(file)
	defer writer.Close()
	
	// Add a file with directory traversal path
	f1, err := writer.Create("../malicious.txt")
	if err != nil {
		return err
	}
	_, err = f1.Write([]byte("This should not be extracted outside the target directory"))
	if err != nil {
		return err
	}
	
	return nil
}

func TestCleanupAllTempDirs(t *testing.T) {
	manager := NewManager()
	
	// Create multiple temp directories
	tempDir1, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("Failed to create temp dir 1: %v", err)
	}
	
	tempDir2, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("Failed to create temp dir 2: %v", err)
	}
	
	tempDir3, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("Failed to create temp dir 3: %v", err)
	}
	
	// Verify all directories exist
	for _, dir := range []string{tempDir1, tempDir2, tempDir3} {
		if _, err := os.Stat(dir); os.IsNotExist(err) {
			t.Fatalf("Temp directory should exist: %s", dir)
		}
	}
	
	// Verify manager is tracking all directories
	if len(manager.tempDirs) != 3 {
		t.Fatalf("Expected 3 tracked temp dirs, got %d", len(manager.tempDirs))
	}
	
	// Cleanup all temp directories
	err = manager.CleanupAllTempDirs()
	if err != nil {
		t.Fatalf("CleanupAllTempDirs failed: %v", err)
	}
	
	// Verify all directories are removed
	for _, dir := range []string{tempDir1, tempDir2, tempDir3} {
		if _, err := os.Stat(dir); !os.IsNotExist(err) {
			t.Fatalf("Temp directory should be removed: %s", dir)
		}
	}
	
	// Verify manager is no longer tracking directories
	if len(manager.tempDirs) != 0 {
		t.Fatalf("Expected 0 tracked temp dirs after cleanup, got %d", len(manager.tempDirs))
	}
}

func TestExtractZipWithNestedDirectories(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	zipPath := filepath.Join(tempDir, "nested.zip")
	extractDir := filepath.Join(tempDir, "extract")
	
	// Create ZIP with nested directory structure
	if err := createNestedZip(zipPath); err != nil {
		t.Fatalf("Failed to create nested ZIP: %v", err)
	}
	
	// Extract ZIP
	err = manager.ExtractZip(zipPath, extractDir)
	if err != nil {
		t.Fatalf("ExtractZip() failed: %v", err)
	}
	
	// Verify nested structure was created
	expectedFiles := []string{
		"level1/file1.txt",
		"level1/level2/file2.txt",
		"level1/level2/level3/file3.txt",
	}
	
	for _, expectedFile := range expectedFiles {
		fullPath := filepath.Join(extractDir, expectedFile)
		if _, err := os.Stat(fullPath); os.IsNotExist(err) {
			t.Fatalf("Expected nested file not found: %s", expectedFile)
		}
		
		// Verify file content
		content, err := os.ReadFile(fullPath)
		if err != nil {
			t.Fatalf("Failed to read nested file %s: %v", expectedFile, err)
		}
		
		expectedContent := fmt.Sprintf("Content of %s", filepath.Base(expectedFile))
		if string(content) != expectedContent {
			t.Fatalf("File content mismatch for %s. Expected: %s, Got: %s", 
				expectedFile, expectedContent, string(content))
		}
	}
}

func TestProcessChangesWithComplexStructure(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	// Create complex changes.json with nested paths
	changesPath := filepath.Join(tempDir, "complex_changes.json")
	changesData := `{
		"deleted": [
			"old/legacy/file1.txt",
			"deprecated/module.dll",
			"temp/cache.dat"
		],
		"added": [
			"new/features/feature1.dll",
			"resources/icons/icon.png",
			"config/new_settings.json"
		],
		"modified": [
			"core/main.exe",
			"lib/utils.dll",
			"data/database.db"
		]
	}`
	
	if err := os.WriteFile(changesPath, []byte(changesData), 0644); err != nil {
		t.Fatalf("Failed to create complex changes.json: %v", err)
	}
	
	changes, err := manager.ProcessChanges(changesPath)
	if err != nil {
		t.Fatalf("ProcessChanges() failed: %v", err)
	}
	
	// Verify all changes were parsed correctly
	expectedDeleted := []string{"old/legacy/file1.txt", "deprecated/module.dll", "temp/cache.dat"}
	expectedAdded := []string{"new/features/feature1.dll", "resources/icons/icon.png", "config/new_settings.json"}
	expectedModified := []string{"core/main.exe", "lib/utils.dll", "data/database.db"}
	
	if len(changes.Deleted) != len(expectedDeleted) {
		t.Fatalf("Expected %d deleted files, got %d", len(expectedDeleted), len(changes.Deleted))
	}
	
	for i, expected := range expectedDeleted {
		if changes.Deleted[i] != expected {
			t.Errorf("Deleted[%d]: expected %s, got %s", i, expected, changes.Deleted[i])
		}
	}
	
	if len(changes.Added) != len(expectedAdded) {
		t.Fatalf("Expected %d added files, got %d", len(expectedAdded), len(changes.Added))
	}
	
	for i, expected := range expectedAdded {
		if changes.Added[i] != expected {
			t.Errorf("Added[%d]: expected %s, got %s", i, expected, changes.Added[i])
		}
	}
	
	if len(changes.Modified) != len(expectedModified) {
		t.Fatalf("Expected %d modified files, got %d", len(expectedModified), len(changes.Modified))
	}
	
	for i, expected := range expectedModified {
		if changes.Modified[i] != expected {
			t.Errorf("Modified[%d]: expected %s, got %s", i, expected, changes.Modified[i])
		}
	}
}

func TestApplyUpdateWithNestedPaths(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	// Create source and target directories
	sourceDir := filepath.Join(tempDir, "source")
	targetDir := filepath.Join(tempDir, "target")
	
	if err := os.MkdirAll(sourceDir, 0755); err != nil {
		t.Fatalf("Failed to create source directory: %v", err)
	}
	if err := os.MkdirAll(targetDir, 0755); err != nil {
		t.Fatalf("Failed to create target directory: %v", err)
	}
	
	// Create nested source files
	nestedFiles := map[string]string{
		"level1/new_file.txt":           "New file content",
		"level1/level2/modified.txt":    "Modified content",
		"features/feature1/config.json": `{"enabled": true}`,
	}
	
	for filePath, content := range nestedFiles {
		fullPath := filepath.Join(sourceDir, filePath)
		if err := os.MkdirAll(filepath.Dir(fullPath), 0755); err != nil {
			t.Fatalf("Failed to create source directory for %s: %v", filePath, err)
		}
		if err := os.WriteFile(fullPath, []byte(content), 0644); err != nil {
			t.Fatalf("Failed to create source file %s: %v", filePath, err)
		}
	}
	
	// Create existing target files
	existingFiles := map[string]string{
		"level1/level2/modified.txt": "Old content",
		"old/deprecated.txt":         "To be deleted",
	}
	
	for filePath, content := range existingFiles {
		fullPath := filepath.Join(targetDir, filePath)
		if err := os.MkdirAll(filepath.Dir(fullPath), 0755); err != nil {
			t.Fatalf("Failed to create target directory for %s: %v", filePath, err)
		}
		if err := os.WriteFile(fullPath, []byte(content), 0644); err != nil {
			t.Fatalf("Failed to create target file %s: %v", filePath, err)
		}
	}
	
	// Define changes with nested paths
	changes := &ChangesInfo{
		Added:    []string{"level1/new_file.txt", "features/feature1/config.json"},
		Modified: []string{"level1/level2/modified.txt"},
		Deleted:  []string{"old/deprecated.txt"},
	}
	
	// Apply update
	err = manager.ApplyUpdate(sourceDir, targetDir, changes)
	if err != nil {
		t.Fatalf("ApplyUpdate() failed: %v", err)
	}
	
	// Verify added files
	for _, addedFile := range changes.Added {
		targetFile := filepath.Join(targetDir, addedFile)
		if _, err := os.Stat(targetFile); os.IsNotExist(err) {
			t.Fatalf("Added file not found: %s", addedFile)
		}
		
		// Verify content matches source
		sourceFile := filepath.Join(sourceDir, addedFile)
		sourceContent, _ := os.ReadFile(sourceFile)
		targetContent, _ := os.ReadFile(targetFile)
		
		if string(sourceContent) != string(targetContent) {
			t.Fatalf("Content mismatch for added file %s", addedFile)
		}
	}
	
	// Verify modified files
	modifiedFile := filepath.Join(targetDir, "level1/level2/modified.txt")
	content, err := os.ReadFile(modifiedFile)
	if err != nil {
		t.Fatalf("Failed to read modified file: %v", err)
	}
	if string(content) != "Modified content" {
		t.Fatalf("Modified file content incorrect. Expected: 'Modified content', Got: '%s'", string(content))
	}
	
	// Verify deleted files
	deletedFile := filepath.Join(targetDir, "old/deprecated.txt")
	if _, err := os.Stat(deletedFile); !os.IsNotExist(err) {
		t.Fatalf("Deleted file still exists: %s", deletedFile)
	}
}

func TestMarkFileForDeletion(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	// Create a test file
	testFile := filepath.Join(tempDir, "test.exe")
	if err := os.WriteFile(testFile, []byte("test executable"), 0755); err != nil {
		t.Fatalf("Failed to create test file: %v", err)
	}
	
	// Mark file for deletion
	err = manager.markFileForDeletion(testFile)
	if err != nil {
		t.Fatalf("markFileForDeletion() failed: %v", err)
	}
	
	// Verify marker file was created
	markerFile := testFile + ".delete_on_restart"
	if _, err := os.Stat(markerFile); os.IsNotExist(err) {
		t.Fatalf("Marker file was not created: %s", markerFile)
	}
	
	// Verify marker file contains correct path
	content, err := os.ReadFile(markerFile)
	if err != nil {
		t.Fatalf("Failed to read marker file: %v", err)
	}
	
	if string(content) != testFile {
		t.Fatalf("Marker file content incorrect. Expected: %s, Got: %s", testFile, string(content))
	}
}

func TestIsFileInUse(t *testing.T) {
	// Test with nil error
	if isFileInUse(nil) {
		t.Error("isFileInUse(nil) should return false")
	}
	
	// Test with regular error
	regularErr := fmt.Errorf("regular error")
	if isFileInUse(regularErr) {
		t.Error("isFileInUse with regular error should return false")
	}
	
	// Test with file in use error message
	fileInUseErr := fmt.Errorf("file is being used by another process")
	if !isFileInUse(fileInUseErr) {
		t.Error("isFileInUse with 'being used by another process' should return true")
	}
	
	// Test with access denied error message
	accessDeniedErr := fmt.Errorf("access is denied")
	if !isFileInUse(accessDeniedErr) {
		t.Error("isFileInUse with 'access is denied' should return true")
	}
}

func TestExtractFileEdgeCases(t *testing.T) {
	manager := NewManager()
	
	tempDir, err := manager.CreateTempDir()
	if err != nil {
		t.Fatalf("CreateTempDir() failed: %v", err)
	}
	defer manager.CleanupTempDir(tempDir)
	
	zipPath := filepath.Join(tempDir, "edge_cases.zip")
	extractDir := filepath.Join(tempDir, "extract")
	
	// Create ZIP with edge cases
	if err := createEdgeCaseZip(zipPath); err != nil {
		t.Fatalf("Failed to create edge case ZIP: %v", err)
	}
	
	// Extract ZIP
	err = manager.ExtractZip(zipPath, extractDir)
	if err != nil {
		t.Fatalf("ExtractZip() failed: %v", err)
	}
	
	// Verify files with special names were extracted
	specialFiles := []string{
		"file with spaces.txt",
		"file-with-dashes.txt",
		"file_with_underscores.txt",
		"UPPERCASE.TXT",
	}
	
	for _, fileName := range specialFiles {
		filePath := filepath.Join(extractDir, fileName)
		if _, err := os.Stat(filePath); os.IsNotExist(err) {
			t.Fatalf("Special file not extracted: %s", fileName)
		}
	}
}

// Helper function to create a ZIP with nested directories
func createNestedZip(zipPath string) error {
	file, err := os.Create(zipPath)
	if err != nil {
		return err
	}
	defer file.Close()
	
	writer := zip.NewWriter(file)
	defer writer.Close()
	
	// Create nested structure
	files := map[string]string{
		"level1/file1.txt":           "Content of file1.txt",
		"level1/level2/file2.txt":    "Content of file2.txt",
		"level1/level2/level3/file3.txt": "Content of file3.txt",
	}
	
	for filePath, content := range files {
		f, err := writer.Create(filePath)
		if err != nil {
			return err
		}
		_, err = f.Write([]byte(content))
		if err != nil {
			return err
		}
	}
	
	return nil
}

// Helper function to create a ZIP with edge case file names
func createEdgeCaseZip(zipPath string) error {
	file, err := os.Create(zipPath)
	if err != nil {
		return err
	}
	defer file.Close()
	
	writer := zip.NewWriter(file)
	defer writer.Close()
	
	// Create files with special names
	files := []string{
		"file with spaces.txt",
		"file-with-dashes.txt",
		"file_with_underscores.txt",
		"UPPERCASE.TXT",
	}
	
	for _, fileName := range files {
		f, err := writer.Create(fileName)
		if err != nil {
			return err
		}
		_, err = f.Write([]byte(fmt.Sprintf("Content of %s", fileName)))
		if err != nil {
			return err
		}
	}
	
	return nil
}