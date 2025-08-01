package assets

import (
	"embed"
	"io/fs"
)

//go:embed config_template.yaml
var EmbeddedAssets embed.FS

// GetConfigTemplate 返回嵌入的配置模板
func GetConfigTemplate() ([]byte, error) {
	return EmbeddedAssets.ReadFile("config_template.yaml")
}

// GetAssetFS 返回嵌入的文件系统
func GetAssetFS() fs.FS {
	return EmbeddedAssets
}

// ListAssets 返回所有嵌入资源的列表
func ListAssets() ([]string, error) {
	var assets []string
	err := fs.WalkDir(EmbeddedAssets, ".", func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if !d.IsDir() {
			assets = append(assets, path)
		}
		return nil
	})
	return assets, err
}
