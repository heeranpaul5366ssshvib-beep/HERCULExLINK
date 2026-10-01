#!/bin/bash
# HERCULE Build Script for Linux/macOS
# Builds all applications for production

set -euo pipefail

VERSION="${1:-1.0.0}"
PLATFORM="${2:-all}"  # all, desktop, mobile, web
SKIP_TESTS="${3:-false}"
CLEAN="${4:-false}"
PACKAGE="${5:-false}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

write_header() {
    echo -e "\n${CYAN}========== $1 ==========${NC}"
}

write_success() {
    echo -e "${GREEN}[SUCCESS] $1${NC}"
}

write_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

write_info() {
    echo -e "${YELLOW}[INFO] $1${NC}"
}

check_prerequisites() {
    write_header "Checking Prerequisites"
    
    NODE_VERSION=$(node --version)
    write_info "Node.js: $NODE_VERSION"
    
    PNPM_VERSION=$(pnpm --version)
    write_info "pnpm: $PNPM_VERSION"
    
    if ! command -v pnpm &> /dev/null; then
        write_error "pnpm not found. Install with: npm install -g pnpm@8"
        exit 1
    fi
}

clean_build() {
    write_header "Cleaning Build Artifacts"
    
    dirs_to_clean=(
        "apps/desktop/dist"
        "apps/desktop/build"
        "apps/mobile/dist"
        "apps/mobile/android/app/build"
        "apps/mobile/ios/build"
        "apps/web/dist"
        "packages/ui/dist"
        "node_modules/.cache"
    )
    
    for dir in "${dirs_to_clean[@]}"; do
        if [ -d "$dir" ]; then
            rm -rf "$dir"
            write_info "Cleaned: $dir"
        fi
    done
    
    write_success "Clean completed"
}

install_dependencies() {
    write_header "Installing Dependencies"
    
    pnpm install --frozen-lockfile
    write_success "Dependencies installed"
}

build_ui_package() {
    write_header "Building UI Package"
    
    cd packages/ui
    pnpm run build
    cd ../..
    write_success "UI package built"
}

build_desktop() {
    write_header "Building Desktop Application (Electron)"
    
    cd apps/desktop
    
    write_info "Building renderer..."
    pnpm run build:renderer
    
    write_info "Building main process..."
    pnpm run build:main
    
    if [ "$PACKAGE" = "true" ]; then
        write_info "Packaging for distribution..."
        pnpm run package
    fi
    
    cd ../..
    write_success "Desktop application built"
}

build_mobile() {
    write_header "Building Mobile Application (Capacitor)"
    
    cd apps/mobile
    
    write_info "Building web assets..."
    pnpm run build
    
    if [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        write_info "Syncing Android..."
        pnpm run build:android
    fi
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        write_info "Syncing iOS..."
        pnpm run build:ios
    fi
    
    cd ../..
    write_success "Mobile application built"
}

build_web() {
    write_header "Building Web Application (Astro SEO Site)"
    
    cd apps/web
    pnpm run build
    cd ../..
    write_success "Web application built"
}

run_tests() {
    if [ "$SKIP_TESTS" = "true" ]; then
        write_info "Skipping tests (SKIP_TESTS=true)"
        return
    fi
    
    write_header "Running Tests"
    
    write_info "Type checking..."
    pnpm run typecheck
    
    write_info "Linting..."
    pnpm run lint
    
    write_info "Running unit tests..."
    pnpm run test
    
    write_success "All tests passed"
}

# Main execution
echo -e "${MAGENTA}🏗️  HERCULE Build Script v$VERSION${NC}"
echo -e "${MAGENTA}Platform: $PLATFORM${NC}"

check_prerequisites

if [ "$CLEAN" = "true" ]; then
    clean_build
fi

install_dependencies
build_ui_package

case "$PLATFORM" in
    "all")
        build_desktop
        build_mobile
        build_web
        ;;
    "desktop")
        build_desktop
        ;;
    "mobile")
        build_mobile
        ;;
    "web")
        build_web
        ;;
    *)
        write_error "Unknown platform: $PLATFORM. Use: all, desktop, mobile, web"
        exit 1
        ;;
esac

run_tests

write_header "Build Complete! 🎉"
write_success "All applications built successfully"

if [ "$PACKAGE" = "true" ]; then
    write_info "Packaged installers available in:"
    write_info "  Desktop: apps/desktop/dist/packages/"
    write_info "  Mobile: apps/mobile/android/app/build/outputs/ & apps/mobile/ios/build/"
    write_info "  Web: apps/web/dist/"
fi