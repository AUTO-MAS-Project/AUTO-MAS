package version

import (
	"fmt"
	"runtime"
)

var (
	// Version is the current version of the application
	Version = "1.0.0"
	
	// BuildTime is set during build time
	BuildTime = "unknown"
	
	// GitCommit is set during build time
	GitCommit = "unknown"
	
	// GoVersion is the Go version used to build
	GoVersion = runtime.Version()
)

// GetVersionInfo returns formatted version information
func GetVersionInfo() string {
	return fmt.Sprintf("Version: %s\nBuild Time: %s\nGit Commit: %s\nGo Version: %s",
		Version, BuildTime, GitCommit, GoVersion)
}

// GetShortVersion returns just the version number
func GetShortVersion() string {
	return Version
}

// GetBuildInfo returns build-specific information
func GetBuildInfo() map[string]string {
	return map[string]string{
		"version":    Version,
		"build_time": BuildTime,
		"git_commit": GitCommit,
		"go_version": GoVersion,
	}
}