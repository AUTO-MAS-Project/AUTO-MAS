package version

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"lightweight-updater/logger"
)

// VersionInfo represents the version information from version.json
type VersionInfo struct {
	MainVersion string                         `json:"main_version"`
	VersionInfo map[string]map[string][]string `json:"version_info"`
}

// ParsedVersion represents a parsed version with major, minor, patch, and beta components
type ParsedVersion struct {
	Major int
	Minor int
	Patch int
	Beta  int
}

// VersionManager handles version-related operations
type VersionManager struct {
	executableDir string
	logger        logger.Logger
}

// NewVersionManager creates a new version manager
func NewVersionManager() *VersionManager {
	execPath, _ := os.Executable()
	execDir := filepath.Dir(execPath)
	return &VersionManager{
		executableDir: execDir,
		logger:        logger.GetDefaultLogger(),
	}
}

// NewVersionManagerWithLogger creates a new version manager with a custom logger
func NewVersionManagerWithLogger(customLogger logger.Logger) *VersionManager {
	execPath, _ := os.Executable()
	execDir := filepath.Dir(execPath)
	return &VersionManager{
		executableDir: execDir,
		logger:        customLogger,
	}
}

// createDefaultVersion creates a default version structure with v0.0.0
func (vm *VersionManager) createDefaultVersion() *VersionInfo {
	return &VersionInfo{
		MainVersion: "0.0.0.0", // Corresponds to v0.0.0
		VersionInfo: make(map[string]map[string][]string),
	}
}

// LoadVersionFromFile loads version information from resources/version.json with fallback handling
func (vm *VersionManager) LoadVersionFromFile() (*VersionInfo, error) {
	versionPath := filepath.Join(vm.executableDir, "resources", "version.json")

	data, err := os.ReadFile(versionPath)
	if err != nil {
		if os.IsNotExist(err) {
			vm.logger.Info("Version file not found at %s, will use default version", versionPath)
			return vm.createDefaultVersion(), nil
		}
		vm.logger.Warn("Failed to read version file at %s: %v, will use default version", versionPath, err)
		return vm.createDefaultVersion(), nil
	}

	var versionInfo VersionInfo
	if err := json.Unmarshal(data, &versionInfo); err != nil {
		vm.logger.Warn("Failed to parse version file at %s: %v, will use default version", versionPath, err)
		return vm.createDefaultVersion(), nil
	}

	vm.logger.Debug("Successfully loaded version information from %s", versionPath)
	return &versionInfo, nil
}

// LoadVersionWithDefault loads version information with guaranteed fallback to default
func (vm *VersionManager) LoadVersionWithDefault() *VersionInfo {
	versionInfo, err := vm.LoadVersionFromFile()
	if err != nil {
		// This should not happen with the updated LoadVersionFromFile, but adding as extra safety
		vm.logger.Error("Unexpected error loading version file: %v, using default version", err)
		return vm.createDefaultVersion()
	}

	// Validate that we have a valid version structure
	if versionInfo == nil {
		vm.logger.Warn("Version info is nil, using default version")
		return vm.createDefaultVersion()
	}

	if versionInfo.MainVersion == "" {
		vm.logger.Warn("Version info has empty main version, using default version")
		return vm.createDefaultVersion()
	}

	if versionInfo.VersionInfo == nil {
		vm.logger.Debug("Version info map is nil, initializing empty map")
		versionInfo.VersionInfo = make(map[string]map[string][]string)
	}

	return versionInfo
}

// ParseVersion parses a version string like "4.4.1.3" into components
func ParseVersion(versionStr string) (*ParsedVersion, error) {
	parts := strings.Split(versionStr, ".")
	if len(parts) < 3 || len(parts) > 4 {
		return nil, fmt.Errorf("invalid version format: %s", versionStr)
	}

	major, err := strconv.Atoi(parts[0])
	if err != nil {
		return nil, fmt.Errorf("invalid major version: %s", parts[0])
	}

	minor, err := strconv.Atoi(parts[1])
	if err != nil {
		return nil, fmt.Errorf("invalid minor version: %s", parts[1])
	}

	patch, err := strconv.Atoi(parts[2])
	if err != nil {
		return nil, fmt.Errorf("invalid patch version: %s", parts[2])
	}

	beta := 0
	if len(parts) == 4 {
		beta, err = strconv.Atoi(parts[3])
		if err != nil {
			return nil, fmt.Errorf("invalid beta version: %s", parts[3])
		}
	}

	return &ParsedVersion{
		Major: major,
		Minor: minor,
		Patch: patch,
		Beta:  beta,
	}, nil
}

// ToVersionString converts a ParsedVersion back to version string format
func (pv *ParsedVersion) ToVersionString() string {
	if pv.Beta == 0 {
		return fmt.Sprintf("%d.%d.%d.0", pv.Major, pv.Minor, pv.Patch)
	}
	return fmt.Sprintf("%d.%d.%d.%d", pv.Major, pv.Minor, pv.Patch, pv.Beta)
}

// ToDisplayVersion converts version to display format (v4.4.0 or v4.4.1-beta3)
func (pv *ParsedVersion) ToDisplayVersion() string {
	if pv.Beta == 0 {
		return fmt.Sprintf("v%d.%d.%d", pv.Major, pv.Minor, pv.Patch)
	}
	return fmt.Sprintf("v%d.%d.%d-beta%d", pv.Major, pv.Minor, pv.Patch, pv.Beta)
}

// GetChannel returns the channel (stable or beta) based on version
func (pv *ParsedVersion) GetChannel() string {
	if pv.Beta == 0 {
		return "stable"
	}
	return "beta"
}

// GetDefaultChannel returns the default channel
func GetDefaultChannel() string {
	return "stable"
}

// IsNewer checks if this version is newer than the other version
func (pv *ParsedVersion) IsNewer(other *ParsedVersion) bool {
	if pv.Major != other.Major {
		return pv.Major > other.Major
	}
	if pv.Minor != other.Minor {
		return pv.Minor > other.Minor
	}
	if pv.Patch != other.Patch {
		return pv.Patch > other.Patch
	}
	return pv.Beta > other.Beta
}
