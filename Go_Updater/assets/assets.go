package assets

import (
	"embed"
	"io/fs"
)

//go:embed config_template.yaml
var EmbeddedAssets embed.FS

// GetConfigTemplate returns the embedded config template
func GetConfigTemplate() ([]byte, error) {
	return EmbeddedAssets.ReadFile("config_template.yaml")
}

// GetAssetFS returns the embedded filesystem
func GetAssetFS() fs.FS {
	return EmbeddedAssets
}

// ListAssets returns a list of all embedded assets
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
