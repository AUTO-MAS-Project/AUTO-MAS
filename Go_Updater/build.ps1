# AUTO_MAA_Go_Updater Build Script (PowerShell)
param(
    [string]$OutputName = "AUTO_MAA_Go_Updater.exe",
    [switch]$Compress = $false
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "AUTO_MAA_Go_Updater Build Script" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Set build variables
$BuildDir = "build"
$DistDir = "dist"
$BuildTime = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssZ")


# Get git commit hash
try {
    $GitCommit = (git rev-parse --short HEAD 2>$null).Trim()
    if (-not $GitCommit) { $GitCommit = "unknown" }
} catch {
    $GitCommit = "unknown"
}

Write-Host "Build Information:" -ForegroundColor Yellow
Write-Host "- Version: $GitCommit"
Write-Host "- Build Time: $BuildTime"
Write-Host "- Git Commit: $GitCommit"
Write-Host "- Target: Windows 64-bit"
Write-Host ""

# Create build directories
if (-not (Test-Path $BuildDir)) { New-Item -ItemType Directory -Path $BuildDir | Out-Null }
if (-not (Test-Path $DistDir)) { New-Item -ItemType Directory -Path $DistDir | Out-Null }

# Set environment variables
$env:GOOS = "windows"
$env:GOARCH = "amd64"
$env:CGO_ENABLED = "1"

# Set build flags
$LdFlags = "-s -w -X AUTO_MAA_Go_Updater/version.Version=$Version -X AUTO_MAA_Go_Updater/version.BuildTime=$BuildTime -X AUTO_MAA_Go_Updater/version.GitCommit=$GitCommit"

Write-Host "Building application..." -ForegroundColor Green

# Ensure icon resource is compiled
if (-not (Test-Path "app.syso")) {
    Write-Host "Compiling icon resource..." -ForegroundColor Yellow
    if (Get-Command rsrc -ErrorAction SilentlyContinue) {
        rsrc -ico icon/AUTO_MAA_Go_Updater.ico -o app.syso
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Warning: Failed to compile icon resource" -ForegroundColor Yellow
        } else {
            Write-Host "Icon resource compiled successfully" -ForegroundColor Green
        }
    } else {
        Write-Host "Warning: rsrc not found. Install with: go install github.com/akavel/rsrc@latest" -ForegroundColor Yellow
    }
}

# Build the application
$BuildCommand = "go build -ldflags=`"$LdFlags`" -o $BuildDir\$OutputName ."
Invoke-Expression $BuildCommand

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed!" -ForegroundColor Red
    exit 1
}

Write-Host "Build completed successfully!" -ForegroundColor Green

# Get file information
$OutputFile = Get-Item "$BuildDir\$OutputName"
$FileSizeMB = [math]::Round($OutputFile.Length / 1MB, 2)

Write-Host ""
Write-Host "Build Results:" -ForegroundColor Yellow
Write-Host "- Output: $($OutputFile.FullName)"
Write-Host "- Size: $($OutputFile.Length) bytes (~$FileSizeMB MB)"


# Optional UPX compression
if ($Compress) {
    Write-Host ""
    Write-Host "Compressing with UPX..." -ForegroundColor Yellow
    
    if (Get-Command upx -ErrorAction SilentlyContinue) {
        upx --best "$BuildDir\$OutputName"
        
        $CompressedFile = Get-Item "$BuildDir\$OutputName"
        $CompressedSizeMB = [math]::Round($CompressedFile.Length / 1MB, 2)
        
        Write-Host "- Compressed Size: $($CompressedFile.Length) bytes (~$CompressedSizeMB MB)" -ForegroundColor Green
    } else {
        Write-Host "UPX not found. Skipping compression." -ForegroundColor Yellow
    }
}

# Copy to dist directory
Copy-Item "$BuildDir\$OutputName" "$DistDir\$OutputName" -Force
Write-Host "- Copied to: $DistDir\$OutputName"

Write-Host ""
Write-Host "Build script completed successfully!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan