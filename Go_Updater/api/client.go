package api

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// MirrorResponse 表示 MirrorChyan API 的响应结构
type MirrorResponse struct {
	Code int    `json:"code"`
	Msg  string `json:"msg"`
	Data struct {
		VersionName   string `json:"version_name"`
		VersionNumber int    `json:"version_number"`
		URL           string `json:"url,omitempty"`
		SHA256        string `json:"sha256,omitempty"`
		Channel       string `json:"channel"`
		OS            string `json:"os"`
		Arch          string `json:"arch"`
		UpdateType    string `json:"update_type,omitempty"`
		ReleaseNote   string `json:"release_note"`
		FileSize      int64  `json:"filesize,omitempty"`
	} `json:"data"`
}

// UpdateCheckParams 表示更新检查的参数
type UpdateCheckParams struct {
	ResourceID     string
	CurrentVersion string
	Channel        string
	UserAgent      string
}

// MirrorClient 定义 Mirror API 客户端的接口方法
type MirrorClient interface {
	CheckUpdate(params UpdateCheckParams) (*MirrorResponse, error)
	IsUpdateAvailable(response *MirrorResponse, currentVersion string) bool
	GetDownloadURL(versionName string) string
}

// Client 实现 MirrorClient 接口
type Client struct {
	httpClient  *http.Client
	baseURL     string
	downloadURL string
}

// NewClient 创建新的 Mirror API 客户端
func NewClient() *Client {
	return &Client{
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		baseURL:     "https://mirrorchyan.com/api/resources",
		downloadURL: "http://221.236.27.82:10197/d/AUTO_MAA",
	}
}

// CheckUpdate 调用 MirrorChyan API 检查更新
func (c *Client) CheckUpdate(params UpdateCheckParams) (*MirrorResponse, error) {
	// 构建 API URL
	apiURL := fmt.Sprintf("%s/%s/latest", c.baseURL, params.ResourceID)

	// 解析 URL 并添加查询参数
	u, err := url.Parse(apiURL)
	if err != nil {
		return nil, fmt.Errorf("解析 API URL 失败: %w", err)
	}

	// 添加查询参数
	q := u.Query()
	q.Set("current_version", params.CurrentVersion)
	q.Set("channel", params.Channel)
	q.Set("os", "")   // 跨平台为空
	q.Set("arch", "") // 跨平台为空
	u.RawQuery = q.Encode()

	// 创建 HTTP 请求
	req, err := http.NewRequest("GET", u.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("创建 HTTP 请求失败: %w", err)
	}

	// 设置 User-Agent 头
	if params.UserAgent != "" {
		req.Header.Set("User-Agent", params.UserAgent)
	} else {
		req.Header.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36")
	}

	// 发送 HTTP 请求
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("发送 HTTP 请求失败: %w", err)
	}
	defer resp.Body.Close()

	// 检查 HTTP 状态码
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API 返回非 200 状态码: %d", resp.StatusCode)
	}

	// 读取响应体
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取响应体失败: %w", err)
	}

	// 解析 JSON 响应
	var mirrorResp MirrorResponse
	if err := json.Unmarshal(body, &mirrorResp); err != nil {
		return nil, fmt.Errorf("解析 JSON 响应失败: %w", err)
	}

	return &mirrorResp, nil
}

// IsUpdateAvailable 比较当前版本与 API 响应中的最新版本
func (c *Client) IsUpdateAvailable(response *MirrorResponse, currentVersion string) bool {
	// 检查 API 响应是否成功
	if response.Code != 0 {
		return false
	}

	// 从响应中获取最新版本
	latestVersion := response.Data.VersionName
	if latestVersion == "" {
		return false
	}

	// 转换版本格式以便比较
	currentVersionNormalized := c.normalizeVersionForComparison(currentVersion)
	latestVersionNormalized := c.normalizeVersionForComparison(latestVersion)

	// 调试输出
	// fmt.Printf("Current: %s -> %s\n", currentVersion, currentVersionNormalized)
	// fmt.Printf("Latest: %s -> %s\n", latestVersion, latestVersionNormalized)
	// fmt.Printf("Compare result: %d\n", compareVersions(currentVersionNormalized, latestVersionNormalized))

	// 使用语义版本比较
	return compareVersions(currentVersionNormalized, latestVersionNormalized) < 0
}

// normalizeVersionForComparison 将不同版本格式转换为可比较格式
func (c *Client) normalizeVersionForComparison(version string) string {
	// 处理 AUTO_MAA 版本格式: "4.4.1.3" -> "v4.4.1-beta3"
	if !strings.HasPrefix(version, "v") && strings.Count(version, ".") == 3 {
		parts := strings.Split(version, ".")
		if len(parts) == 4 {
			major, minor, patch, beta := parts[0], parts[1], parts[2], parts[3]
			if beta == "0" {
				return fmt.Sprintf("v%s.%s.%s", major, minor, patch)
			} else {
				return fmt.Sprintf("v%s.%s.%s-beta%s", major, minor, patch, beta)
			}
		}
	}

	// 如果已经是标准格式则直接返回
	return version
}

// compareVersions 比较两个语义版本字符串
// 返回值: -1 如果 v1 < v2, 0 如果 v1 == v2, 1 如果 v1 > v2
func compareVersions(v1, v2 string) int {
	// 通过移除 'v' 前缀来标准化版本
	v1 = normalizeVersion(v1)
	v2 = normalizeVersion(v2)

	// 解析版本组件
	parts1 := parseVersionParts(v1)
	parts2 := parseVersionParts(v2)

	// 比较前三个组件 (major.minor.patch)
	for i := 0; i < 3; i++ {
		var p1, p2 int
		if i < len(parts1) {
			p1 = parts1[i]
		}
		if i < len(parts2) {
			p2 = parts2[i]
		}

		if p1 < p2 {
			return -1
		} else if p1 > p2 {
			return 1
		}
	}

	// 如果前三个组件相同，比较beta版本号
	var beta1, beta2 int
	if len(parts1) > 3 {
		beta1 = parts1[3]
	}
	if len(parts2) > 3 {
		beta2 = parts2[3]
	}

	// 特殊处理beta版本比较：
	// - 如果一个是正式版(beta=0)，另一个是beta版(beta>0)，正式版更新
	// - 如果都是beta版，比较beta版本号
	if beta1 == 0 && beta2 > 0 {
		return 1  // 正式版比beta版更新
	}
	if beta1 > 0 && beta2 == 0 {
		return -1 // beta版比正式版旧
	}
	
	// 都是正式版或都是beta版，直接比较
	if beta1 < beta2 {
		return -1
	} else if beta1 > beta2 {
		return 1
	}

	return 0
}

// normalizeVersion 移除 'v' 前缀并处理常见版本格式
func normalizeVersion(version string) string {
	if len(version) > 0 && (version[0] == 'v' || version[0] == 'V') {
		return version[1:]
	}
	return version
}

// parseVersionParts 将版本字符串解析为数字组件，包括beta版本号
func parseVersionParts(version string) []int {
	if version == "" {
		return []int{0}
	}

	parts := make([]int, 0, 4)
	current := 0

	// 先检查是否包含 -beta
	betaIndex := strings.Index(version, "-beta")
	var mainVersion, betaVersion string
	
	if betaIndex != -1 {
		mainVersion = version[:betaIndex]
		betaVersion = version[betaIndex+5:] // 跳过 "-beta"
	} else {
		mainVersion = version
		betaVersion = ""
	}

	// 解析主版本号 (major.minor.patch)
	for _, char := range mainVersion {
		if char >= '0' && char <= '9' {
			current = current*10 + int(char-'0')
		} else if char == '.' {
			parts = append(parts, current)
			current = 0
		} else {
			// 遇到非数字非点字符，停止解析
			break
		}
	}
	// 添加最后一个主版本组件
	parts = append(parts, current)

	// 确保至少有 3 个组件 (major.minor.patch)
	for len(parts) < 3 {
		parts = append(parts, 0)
	}

	// 解析beta版本号
	if betaVersion != "" {
		// 跳过可能的点号
		if strings.HasPrefix(betaVersion, ".") {
			betaVersion = betaVersion[1:]
		}
		
		betaNum := 0
		for _, char := range betaVersion {
			if char >= '0' && char <= '9' {
				betaNum = betaNum*10 + int(char-'0')
			} else {
				break
			}
		}
		// Beta版本号保持正数，但在比较时会特殊处理
		parts = append(parts, betaNum)
	} else {
		// 非beta版本，添加0作为beta版本号
		parts = append(parts, 0)
	}

	return parts
}

// GetDownloadURL 根据版本名生成下载站的下载 URL
func (c *Client) GetDownloadURL(versionName string) string {
	// 将版本名转换为文件名格式
	// 例如: "v4.4.0" -> "AUTO_MAA_v4.4.0.zip"
	// 例如: "v4.4.1-beta3" -> "AUTO_MAA_v4.4.1-beta.3.zip"
	filename := fmt.Sprintf("AUTO_MAA_%s.zip", versionName)

	// 处理 beta 版本: 将 "beta3" 转换为 "beta.3"
	if strings.Contains(filename, "-beta") && !strings.Contains(filename, "-beta.") {
		filename = strings.Replace(filename, "-beta", "-beta.", 1)
	}

	return fmt.Sprintf("%s/%s", c.downloadURL, filename)
}
