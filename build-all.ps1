<#
.SYNOPSIS
    Build all HERCULE applications for production

.DESCRIPTION
    This script builds the desktop (Electron), mobile (Capacitor), and web (Astro) applications
    with proper configuration for production releases.

.NOTES
    Requires: Node.js 20+, pnpm 8+, Rust (for Tauri alternative), Java 17+ (for Android)
#>

param(
    [string]$Version = "1.0.0",
    [string]$Platform = "all", # all, desktop, mobile, web
    [switch]$SkipTests,
    [switch]$Clean,
    [switch]$Package
)

$ErrorActionPreference = "Stop"

function Write-Header($message) {
    Write-Host "`n========== $message ==========" -ForegroundColor Cyan
}

function Write-Success($message) {
    Write-Host "[SUCCESS] $message" -ForegroundColor Green
}

function Write-Error($message) {
    Write-Host "[ERROR] $message" -ForegroundColor Red
}

function Write-Info($message) {
    Write-Host "[INFO] $message" -ForegroundColor Yellow
}

# Check prerequisites
function Check-Prerequisites {
    Write-Header "Checking Prerequisites"
    
    $nodeVersion = node --version
    Write-Info "Node.js: $nodeVersion"
    
    $pnpmVersion = pnpm --version
    Write-Info "pnpm: $pnpmVersion"
    
    if (-not (Get-Command "pnpm" -ErrorAction SilentlyContinue)) {
        Write-Error "pnpm not found. Install with: npm install -g pnpm@8"
        exit 1
    }
}

# Clean build artifacts
function Clean-Build {
    Write-Header "Cleaning Build Artifacts"
    
    $dirsToClean = @(
        "apps/desktop/dist",
        "apps/desktop/build",
        "apps/mobile/dist",
        "apps/mobile/android/app/build",
        "apps/mobile/ios/build",
        "apps/web/dist",
        "packages/ui/dist",
        "node_modules/.cache"
    )
    
    foreach ($dir in $dirsToClean) {
        if (Test-Path $dir) {
            Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
            Write-Info "Cleaned: $dir"
        }
    }
    
    Write-Success "Clean completed"
}

# Install dependencies
function Install-Dependencies {
    Write-Header "Installing Dependencies"
    
    pnpm install --frozen-lockfile
    Write-Success "Dependencies installed"
}

# Build UI package
function Build-UIPackage {
    Write-Header "Building UI Package"
    
    Set-Location "packages/ui"
    pnpm run build
    Set-Location "../.."
    Write-Success "UI package built"
}

# Build Desktop (Electron)
function Build-Desktop {
    Write-Header "Building Desktop Application"
    
    Set-Location "apps/desktop"
    
    Write-Info "Building renderer..."
    pnpm run build:renderer
    
    Write-Info "Building main process..."
    pnpm run build:main
    
    if ($Package) {
        Write-Info "Packaging for distribution..."
        pnpm run package
    }
    
    Set-Location "../.."
    Write-Success "Desktop application built"
}

# Build Mobile (Capacitor)
function Build-Mobile {
    Write-Header "Building Mobile Application"
    
    Set-Location "apps/mobile"
    
    Write-Info "Building web assets..."
    pnpm run build
    
    if ($IsWindows -or $IsLinux) {
        Write-Info "Syncing Android..."
        pnpm run build:android
    }
    
    if ($IsMacOS) {
        Write-Info "Syncing iOS..."
        pnpm run build:ios
    }
    
    Set-Location "../.."
    Write-Success "Mobile application built"
}

# Build Web (Astro)
function Build-Web {
    Write-Header "Building Web Application (SEO Site)"
    
    Set-Location "apps/web"
    pnpm run build
    Set-Location "../.."
    Write-Success "Web application built"
}

# Run tests
function Run-Tests {
    if ($SkipTests) {
        Write-Info "Skipping tests (--SkipTests flag)"
        return
    }
    
    Write-Header "Running Tests"
    
    # TypeScript type checking
    Write-Info "Type checking..."
    pnpm run typecheck
    
    # Linting
    Write-Info "Linting..."
    pnpm run lint
    
    # Unit tests
    Write-Info "Running unit tests..."
    pnpm run test
    
    Write-Success "All tests passed"
}

# Main execution
try {
    Write-Host "🏗️  HERCULE Build Script v$Version" -ForegroundColor Magenta
    Write-Host "Platform: $Platform" -ForegroundColor Magenta
    
    Check-Prerequisites
    
    if ($Clean) {
        Clean-Build
    }
    
    Install-Dependencies
    Build-UIPackage
    
    switch ($Platform.ToLower()) {
        "all" {
            Build-Desktop
            Build-Mobile
            Build-Web
        }
        "desktop" {
            Build-Desktop
        }
        "mobile" {
            Build-Mobile
        }
        "web" {
            Build-Web
        }
        default {
            Write-Error "Unknown platform: $Platform. Use: all, desktop, mobile, web"
            exit 1
        }
    }
    
    Run-Tests
    
    Write-Header "Build Complete! 🎉"
    Write-Success "All applications built successfully"
    
    if ($Package) {
        Write-Info "Packaged installers available in:"
        Write-Info "  Desktop: apps/desktop/dist/packages/"
        Write-Info "  Mobile: apps/mobile/android/app/build/outputs/ & apps/mobile/ios/build/"
        Write-Info "  Web: apps/web/dist/"
    }
    
} catch {
    Write-Error "Build failed: $_"
    exit 1
}