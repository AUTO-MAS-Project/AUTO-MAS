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

// MirrorResponse represents the response from MirrorChyan API
type MirrorResponse struct {
	Code int    `json:"code"`
	Msg  string `json:"msg"`
	Data struct {
		VersionName     string `json:"version_name"`
		VersionNumber   int    `json:"version_number"`
		URL             string `json:"url,omitempty"`           // Only present when using CDK
		SHA256          string `json:"sha256,omitempty"`        // Only present when using CDK
		Channel         string `json:"channel"`
		OS              string `json:"os"`
		Arch            string `json:"arch"`
		UpdateType      string `json:"update_type,omitempty"`   // Only present when using CDK
		ReleaseNote     string `json:"release_note"`
		FileSize        int64  `json:"filesize,omitempty"`      // Only present when using CDK
		CDKExpiredTime  int64  `json:"cdk_expired_time,omitempty"` // Only present when using CDK
	} `json:"data"`
}

// UpdateCheckParams represents parameters for update checking
type UpdateCheckParams struct {
	ResourceID     string
	CurrentVersion string
	Channel        string
	CDK            string
	UserAgent      string
}

// MirrorClient interface defines the methods for Mirror API client
type MirrorClient interface {
	CheckUpdate(params UpdateCheckParams) (*MirrorResponse, error)
	CheckUpdateLegacy(resourceID, currentVersion, cdk, userAgent string) (*MirrorResponse, error)
	IsUpdateAvailable(response *MirrorResponse, currentVersion string) bool
	GetOfficialDownloadURL(versionName string) string
}

// Client implements MirrorClient interface
type Client struct {
	httpClient *http.Client
	baseURL    string
}

// NewClient creates a new Mirror API client
func NewClient() *Client {
	return &Client{
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		baseURL: "https://mirrorchyan.com/api/resources",
	}
}

// CheckUpdate calls MirrorChyan API to check for updates with new parameter structure
func (c *Client) CheckUpdate(params UpdateCheckParams) (*MirrorResponse, error) {
	// Construct the API URL
	apiURL := fmt.Sprintf("%s/%s/latest", c.baseURL, params.ResourceID)
	
	// Parse URL to add query parameters
	u, err := url.Parse(apiURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse API URL: %w", err)
	}
	
	// Add query parameters
	q := u.Query()
	q.Set("current_version", params.CurrentVersion)
	q.Set("channel", params.Channel)
	q.Set("os", "")    // Empty for cross-platform
	q.Set("arch", "")  // Empty for cross-platform
	
	if params.CDK != "" {
		q.Set("cdk", params.CDK)
	}
	u.RawQuery = q.Encode()
	
	// Create HTTP request
	req, err := http.NewRequest("GET", u.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create HTTP request: %w", err)
	}
	
	// Set User-Agent header
	if params.UserAgent != "" {
		req.Header.Set("User-Agent", params.UserAgent)
	} else {
		req.Header.Set("User-Agent", "LightweightUpdater/1.0")
	}
	
	// Make HTTP request
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to make HTTP request: %w", err)
	}
	defer resp.Body.Close()
	
	// Check HTTP status code
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API returned non-200 status code: %d", resp.StatusCode)
	}
	
	// Read response body
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}
	
	// Parse JSON response
	var mirrorResp MirrorResponse
	if err := json.Unmarshal(body, &mirrorResp); err != nil {
		return nil, fmt.Errorf("failed to parse JSON response: %w", err)
	}
	
	return &mirrorResp, nil
}

// CheckUpdateLegacy calls Mirror API to check for updates (legacy method for backward compatibility)
func (c *Client) CheckUpdateLegacy(resourceID, currentVersion, cdk, userAgent string) (*MirrorResponse, error) {
	// Construct the API URL
	apiURL := fmt.Sprintf("%s/%s/latest", c.baseURL, resourceID)
	
	// Parse URL to add query parameters
	u, err := url.Parse(apiURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse API URL: %w", err)
	}
	
	// Add query parameters
	q := u.Query()
	q.Set("current_version", currentVersion)
	if cdk != "" {
		q.Set("cdk", cdk)
	}
	u.RawQuery = q.Encode()
	
	// Create HTTP request
	req, err := http.NewRequest("GET", u.String(), nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create HTTP request: %w", err)
	}
	
	// Set User-Agent header
	if userAgent != "" {
		req.Header.Set("User-Agent", userAgent)
	} else {
		req.Header.Set("User-Agent", "LightweightUpdater/1.0")
	}
	
	// Make HTTP request
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to make HTTP request: %w", err)
	}
	defer resp.Body.Close()
	
	// Check HTTP status code
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("API returned non-200 status code: %d", resp.StatusCode)
	}
	
	// Read response body
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("failed to read response body: %w", err)
	}
	
	// Parse JSON response
	var mirrorResp MirrorResponse
	if err := json.Unmarshal(body, &mirrorResp); err != nil {
		return nil, fmt.Errorf("failed to parse JSON response: %w", err)
	}
	
	return &mirrorResp, nil
}

// IsUpdateAvailable compares current version with the latest version from API response
func (c *Client) IsUpdateAvailable(response *MirrorResponse, currentVersion string) bool {
	// Check if API response is successful
	if response.Code != 0 {
		return false
	}
	
	// Get latest version from response
	latestVersion := response.Data.VersionName
	if latestVersion == "" {
		return false
	}
	
	// Convert version formats for comparison
	currentVersionNormalized := c.normalizeVersionForComparison(currentVersion)
	latestVersionNormalized := c.normalizeVersionForComparison(latestVersion)
	
	// Compare versions using semantic version comparison
	return compareVersions(currentVersionNormalized, latestVersionNormalized) < 0
}

// normalizeVersionForComparison converts different version formats to comparable format
func (c *Client) normalizeVersionForComparison(version string) string {
	// Handle AUTO_MAA version format: "4.4.1.3" -> "v4.4.1-beta3"
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
	
	// Return as-is if already in standard format
	return version
}

// compareVersions compares two semantic version strings
// Returns: -1 if v1 < v2, 0 if v1 == v2, 1 if v1 > v2
func compareVersions(v1, v2 string) int {
	// Normalize versions by removing 'v' prefix if present
	v1 = normalizeVersion(v1)
	v2 = normalizeVersion(v2)
	
	// Parse version components
	parts1 := parseVersionParts(v1)
	parts2 := parseVersionParts(v2)
	
	// Compare each component
	maxLen := len(parts1)
	if len(parts2) > maxLen {
		maxLen = len(parts2)
	}
	
	for i := 0; i < maxLen; i++ {
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
	
	return 0
}

// normalizeVersion removes 'v' prefix and handles common version formats
func normalizeVersion(version string) string {
	if len(version) > 0 && (version[0] == 'v' || version[0] == 'V') {
		return version[1:]
	}
	return version
}

// parseVersionParts parses version string into numeric components
func parseVersionParts(version string) []int {
	if version == "" {
		return []int{0}
	}
	
	parts := make([]int, 0, 3)
	current := 0
	
	for _, char := range version {
		if char >= '0' && char <= '9' {
			current = current*10 + int(char-'0')
		} else if char == '.' {
			parts = append(parts, current)
			current = 0
		} else {
			// Stop parsing at non-numeric, non-dot characters (like pre-release identifiers)
			break
		}
	}
	
	// Add the last component
	parts = append(parts, current)
	
	// Ensure at least 3 components (major.minor.patch)
	for len(parts) < 3 {
		parts = append(parts, 0)
	}
	
	return parts
}

// GetOfficialDownloadURL generates the official download URL based on version name
func (c *Client) GetOfficialDownloadURL(versionName string) string {
	// Official download site base URL
	baseURL := "http://221.236.27.82:10197/d/AUTO_MAA"
	
	// Convert version name to filename format
	// e.g., "v4.4.0" -> "AUTO_MAA_v4.4.0.zip"
	// e.g., "v4.4.1-beta3" -> "AUTO_MAA_v4.4.1-beta.3.zip"
	filename := fmt.Sprintf("AUTO_MAA_%s.zip", versionName)
	
	// Handle beta versions: convert "beta3" to "beta.3"
	if strings.Contains(filename, "-beta") && !strings.Contains(filename, "-beta.") {
		filename = strings.Replace(filename, "-beta", "-beta.", 1)
	}
	
	return fmt.Sprintf("%s/%s", baseURL, filename)
}

// HasCDKDownloadURL checks if the response contains a CDK download URL
func (c *Client) HasCDKDownloadURL(response *MirrorResponse) bool {
	return response != nil && response.Data.URL != ""
}

// GetDownloadURL returns the appropriate download URL based on available options
func (c *Client) GetDownloadURL(response *MirrorResponse) string {
	if c.HasCDKDownloadURL(response) {
		return response.Data.URL
	}
	return c.GetOfficialDownloadURL(response.Data.VersionName)
}