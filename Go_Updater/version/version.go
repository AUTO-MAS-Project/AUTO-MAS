package version

import (
	"runtime"
)

var (
	// Version 应用程序的当前版本
	Version = "1.0.0"

	// BuildTime 在构建时设置
	BuildTime = "unknown"

	// GitCommit 在构建时设置
	GitCommit = "unknown"

	// GoVersion 用于构建的 Go 版本
	GoVersion = runtime.Version()
)
