# AUTO_MAA_Go_Updater Makefile

# Build variables
VERSION ?= 1.0.0
BUILD_TIME := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")
GIT_COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
OUTPUT_NAME := AUTO_MAA_Go_Updater
BUILD_DIR := build
DIST_DIR := dist

# Go build flags
LDFLAGS := -s -w -X AUTO_MAA_Go_Updater/version.Version=$(VERSION) -X AUTO_MAA_Go_Updater/version.BuildTime=$(BUILD_TIME) -X AUTO_MAA_Go_Updater/version.GitCommit=$(GIT_COMMIT)

# Default target
.PHONY: all
all: clean build

# Clean build artifacts
.PHONY: clean
clean:
	@echo "Cleaning build artifacts..."
	@rm -rf $(BUILD_DIR) $(DIST_DIR)
	@mkdir -p $(BUILD_DIR) $(DIST_DIR)

# Build for Windows 64-bit
.PHONY: build
build: clean
	@echo "========================================="
	@echo "Building AUTO_MAA_Go_Updater"
	@echo "========================================="
	@echo "Version: $(VERSION)"
	@echo "Build Time: $(BUILD_TIME)"
	@echo "Git Commit: $(GIT_COMMIT)"
	@echo "Target: Windows 64-bit"
	@echo ""
	@echo "Building application..."
	@GOOS=windows GOARCH=amd64 CGO_ENABLED=1 go build -ldflags="$(LDFLAGS)" -o $(BUILD_DIR)/$(OUTPUT_NAME).exe .
	@echo "Build completed successfully!"
	@echo ""
	@echo "Build Results:"
	@ls -lh $(BUILD_DIR)/$(OUTPUT_NAME).exe
	@cp $(BUILD_DIR)/$(OUTPUT_NAME).exe $(DIST_DIR)/$(OUTPUT_NAME).exe
	@echo "Copied to: $(DIST_DIR)/$(OUTPUT_NAME).exe"

# Build with UPX compression
.PHONY: build-compressed
build-compressed: build
	@echo ""
	@echo "Compressing with UPX..."
	@if command -v upx >/dev/null 2>&1; then \
		upx --best $(BUILD_DIR)/$(OUTPUT_NAME).exe; \
		echo "Compression completed!"; \
		ls -lh $(BUILD_DIR)/$(OUTPUT_NAME).exe; \
		cp $(BUILD_DIR)/$(OUTPUT_NAME).exe $(DIST_DIR)/$(OUTPUT_NAME).exe; \
	else \
		echo "UPX not found. Skipping compression."; \
	fi

# Run tests
.PHONY: test
test:
	@echo "Running tests..."
	@go test -v ./...

# Run with version flag
.PHONY: version
version: build
	@echo ""
	@echo "Testing version information:"
	@$(BUILD_DIR)/$(OUTPUT_NAME).exe -version

# Install dependencies
.PHONY: deps
deps:
	@echo "Installing dependencies..."
	@go mod tidy
	@go mod download

# Format code
.PHONY: fmt
fmt:
	@echo "Formatting code..."
	@go fmt ./...

# Lint code
.PHONY: lint
lint:
	@echo "Linting code..."
	@if command -v golangci-lint >/dev/null 2>&1; then \
		golangci-lint run; \
	else \
		echo "golangci-lint not found. Install it with: go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest"; \
	fi

# Development build (faster, no optimizations)
.PHONY: dev
dev:
	@echo "Building development version..."
	@go build -o $(BUILD_DIR)/$(OUTPUT_NAME)-dev.exe .
	@echo "Development build completed: $(BUILD_DIR)/$(OUTPUT_NAME)-dev.exe"

# Help
.PHONY: help
help:
	@echo "Available targets:"
	@echo "  all              - Clean and build (default)"
	@echo "  build            - Build for Windows 64-bit"
	@echo "  build-compressed - Build and compress with UPX"
	@echo "  clean            - Clean build artifacts"
	@echo "  test             - Run tests"
	@echo "  version          - Build and show version"
	@echo "  deps             - Install dependencies"
	@echo "  fmt              - Format code"
	@echo "  lint             - Lint code"
	@echo "  dev              - Development build"
	@echo "  help             - Show this help"