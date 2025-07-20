@echo off
setlocal enabledelayedexpansion

echo ========================================
echo AUTO_MAA_Go_Updater Build Script
echo ========================================

:: Set build variables
set VERSION=1.0.0
set OUTPUT_NAME=AUTO_MAA_Go_Updater.exe
set BUILD_DIR=build
set DIST_DIR=dist

:: Get current timestamp
for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value') do set "dt=%%a"
set "YY=%dt:~2,2%" & set "YYYY=%dt:~0,4%" & set "MM=%dt:~4,2%" & set "DD=%dt:~6,2%"
set "HH=%dt:~8,2%" & set "Min=%dt:~10,2%" & set "Sec=%dt:~12,2%"
set "BUILD_TIME=%YYYY%-%MM%-%DD%T%HH%:%Min%:%Sec%Z"

:: Get git commit hash (if available)
git rev-parse --short HEAD > temp_commit.txt 2>nul
if exist temp_commit.txt (
    set /p GIT_COMMIT=<temp_commit.txt
    del temp_commit.txt
) else (
    set GIT_COMMIT=unknown
)

echo Build Information:
echo - Version: %VERSION%
echo - Build Time: %BUILD_TIME%
echo - Git Commit: %GIT_COMMIT%
echo - Target: Windows 64-bit
echo.

:: Create build directories
if not exist %BUILD_DIR% mkdir %BUILD_DIR%
if not exist %DIST_DIR% mkdir %DIST_DIR%

:: Set build flags
set LDFLAGS=-s -w -X lightweight-updater/version.Version=%VERSION% -X lightweight-updater/version.BuildTime=%BUILD_TIME% -X lightweight-updater/version.GitCommit=%GIT_COMMIT%

echo Building application...

:: Ensure icon resource is compiled
if not exist app.syso (
    echo Compiling icon resource...
    where rsrc >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        rsrc -ico icon\AUTO_MAA_Go_Updater.ico -o app.syso
        if !ERRORLEVEL! equ 0 (
            echo Icon resource compiled successfully
        ) else (
            echo Warning: Failed to compile icon resource
        )
    ) else (
        echo Warning: rsrc not found. Install with: go install github.com/akavel/rsrc@latest
    )
)

set GOOS=windows
set GOARCH=amd64
set CGO_ENABLED=1

:: Build the application
go build -ldflags="%LDFLAGS%" -o %BUILD_DIR%\%OUTPUT_NAME% .

if %ERRORLEVEL% neq 0 (
    echo Build failed!
    exit /b 1
)

echo Build completed successfully!

:: Get file size
for %%A in (%BUILD_DIR%\%OUTPUT_NAME%) do set FILE_SIZE=%%~zA

:: Convert bytes to MB
set /a FILE_SIZE_MB=%FILE_SIZE%/1024/1024

echo.
echo Build Results:
echo - Output: %BUILD_DIR%\%OUTPUT_NAME%
echo - Size: %FILE_SIZE% bytes (~%FILE_SIZE_MB% MB)

:: Check if file size is within requirements (<10MB)
if %FILE_SIZE_MB% gtr 10 (
    echo WARNING: File size exceeds 10MB requirement!
) else (
    echo File size meets requirements (^<10MB)
)

:: Copy to dist directory
copy %BUILD_DIR%\%OUTPUT_NAME% %DIST_DIR%\%OUTPUT_NAME% >nul
echo - Copied to: %DIST_DIR%\%OUTPUT_NAME%

echo.
echo Build script completed successfully!
echo ========================================