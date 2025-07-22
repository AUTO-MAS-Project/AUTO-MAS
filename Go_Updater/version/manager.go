package version

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"AUTO_MAA_Go_Updater/logger"
)

// VersionInfo 表示来自 version.json 的版本信息
type VersionInfo struct {
	MainVersion string                         `json:"main_version"`
	VersionInfo map[string]map[string][]string `json:"version_info"`
}

// ParsedVersion 表示解析后的版本，包含主版本号、次版本号、补丁版本号和测试版本号组件
type ParsedVersion struct {
	Major int
	Minor int
	Patch int
	Beta  int
}

// VersionManager 处理版本相关操作
type VersionManager struct {
	executableDir string
	logger        logger.Logger
}

// NewVersionManager 创建新的版本管理器
func NewVersionManager() *VersionManager {
	execPath, _ := os.Executable()
	execDir := filepath.Dir(execPath)
	return &VersionManager{
		executableDir: execDir,
		logger:        logger.GetDefaultLogger(),
	}
}

// createDefaultVersion 创建默认版本结构 v0.0.0
func (vm *VersionManager) createDefaultVersion() *VersionInfo {
	return &VersionInfo{
		MainVersion: "0.0.0.0", // 对应 v0.0.0
		VersionInfo: make(map[string]map[string][]string),
	}
}

// LoadVersionFromFile 从 resources/version.json 加载版本信息并处理回退
func (vm *VersionManager) LoadVersionFromFile() (*VersionInfo, error) {
	versionPath := filepath.Join(vm.executableDir, "resources", "version.json")

	data, err := os.ReadFile(versionPath)
	if err != nil {
		if os.IsNotExist(err) {
			fmt.Println("未读取到版本信息，使用默认版本进行更新。")
			return vm.createDefaultVersion(), nil
		}
		vm.logger.Warn("读取版本文件 %s 失败: %v，将使用默认版本", versionPath, err)
		return vm.createDefaultVersion(), nil
	}

	var versionInfo VersionInfo
	if err := json.Unmarshal(data, &versionInfo); err != nil {
		vm.logger.Warn("解析版本文件 %s 失败: %v，将使用默认版本", versionPath, err)
		return vm.createDefaultVersion(), nil
	}

	vm.logger.Debug("成功从 %s 加载版本信息", versionPath)
	return &versionInfo, nil
}

// LoadVersionWithDefault 加载版本信息并保证回退到默认版本
func (vm *VersionManager) LoadVersionWithDefault() *VersionInfo {
	versionInfo, err := vm.LoadVersionFromFile()
	if err != nil {
		// 这在更新的 LoadVersionFromFile 中不应该发生，但添加作为额外安全措施
		vm.logger.Error("加载版本文件时出现意外错误: %v，使用默认版本", err)
		return vm.createDefaultVersion()
	}

	// 验证我们有一个有效的版本结构
	if versionInfo == nil {
		vm.logger.Warn("版本信息为空，使用默认版本")
		return vm.createDefaultVersion()
	}

	if versionInfo.MainVersion == "" {
		vm.logger.Warn("版本信息主版本为空，使用默认版本")
		return vm.createDefaultVersion()
	}

	if versionInfo.VersionInfo == nil {
		vm.logger.Debug("版本信息映射为空，初始化空映射")
		versionInfo.VersionInfo = make(map[string]map[string][]string)
	}

	return versionInfo
}

// ParseVersion 解析版本字符串如 "4.4.1.3" 为组件
func ParseVersion(versionStr string) (*ParsedVersion, error) {
	parts := strings.Split(versionStr, ".")
	if len(parts) < 3 || len(parts) > 4 {
		return nil, fmt.Errorf("无效的版本格式: %s", versionStr)
	}

	major, err := strconv.Atoi(parts[0])
	if err != nil {
		return nil, fmt.Errorf("无效的主版本号: %s", parts[0])
	}

	minor, err := strconv.Atoi(parts[1])
	if err != nil {
		return nil, fmt.Errorf("无效的次版本号: %s", parts[1])
	}

	patch, err := strconv.Atoi(parts[2])
	if err != nil {
		return nil, fmt.Errorf("无效的补丁版本号: %s", parts[2])
	}

	beta := 0
	if len(parts) == 4 {
		beta, err = strconv.Atoi(parts[3])
		if err != nil {
			return nil, fmt.Errorf("无效的测试版本号: %s", parts[3])
		}
	}

	return &ParsedVersion{
		Major: major,
		Minor: minor,
		Patch: patch,
		Beta:  beta,
	}, nil
}

// ToVersionString 将 ParsedVersion 转换回版本字符串格式
func (pv *ParsedVersion) ToVersionString() string {
	if pv.Beta == 0 {
		return fmt.Sprintf("%d.%d.%d.0", pv.Major, pv.Minor, pv.Patch)
	}
	return fmt.Sprintf("%d.%d.%d.%d", pv.Major, pv.Minor, pv.Patch, pv.Beta)
}

// ToDisplayVersion 将版本转换为显示格式 (v4.4.0 或 v4.4.1-beta3)
func (pv *ParsedVersion) ToDisplayVersion() string {
	if pv.Beta == 0 {
		return fmt.Sprintf("v%d.%d.%d", pv.Major, pv.Minor, pv.Patch)
	}
	return fmt.Sprintf("v%d.%d.%d-beta%d", pv.Major, pv.Minor, pv.Patch, pv.Beta)
}

// GetChannel 根据版本返回渠道 (stable 或 beta)
func (pv *ParsedVersion) GetChannel() string {
	if pv.Beta == 0 {
		return "stable"
	}
	return "beta"
}

// IsNewer 检查此版本是否比其他版本更新
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
