# HERCULE - Your Local AI Assistant

A production-ready, cross-platform AI assistant that runs entirely on your device. Private, offline, and free.

## Features

- **100% Local** - Your data never leaves your device
- **Multi-Platform** - Windows, macOS, Linux, iOS, Android, and Web
- **Model Management** - Download, manage, and switch between quantized GGUF models
- **Hardware Acceleration** - Apple Silicon, NVIDIA CUDA, AMD ROCm, Intel GPU support
- **Extensible** - Plugin system for GitHub, VS Code, Google Drive, Web Search, and more
- **Developer-First** - Built-in code execution, project analysis, debugging assistance
- **Autonomous Agents** - Set goals, not prompts

## Monorepo Structure

```
hercule/
├── apps/
│   ├── desktop/          # Electron + React + TypeScript
│   ├── mobile/           # Capacitor + React + TypeScript
│   └── web/              # Astro + Tailwind (SEO site)
├── packages/
│   └── ui/               # Shared React component library
├── .github/
│   └── workflows/        # CI/CD pipelines
└── build scripts         # build-all.ps1 / build-all.sh
```

## Quick Start

### Prerequisites

- Node.js 20+
- pnpm 8+
- Rust (optional, for native modules)
- Java 17+ (for Android builds)

### Install Dependencies

```bash
pnpm install
```

### Development

```bash
# Start all development servers
pnpm dev

# Start individual apps
pnpm dev:desktop    # Electron app at http://localhost:5173
pnpm dev:mobile     # Capacitor app
pnpm dev:web        # Astro site at http://localhost:4321
```

### Building for Production

#### Windows (PowerShell)
```powershell
# Build everything
.\build-all.ps1 -Version "1.0.0" -Platform all -Package

# Build specific platform
.\build-all.ps1 -Platform desktop -Package
.\build-all.ps1 -Platform mobile -Package
.\build-all.ps1 -Platform web
```

#### Linux/macOS (Bash)
```bash
# Make executable first
chmod +x build-all.sh

# Build everything
./build-all.sh 1.0.0 all true false true

# Build specific platform
./build-all.sh 1.0.0 desktop true false true
./build-all.sh 1.0.0 mobile true false true
./build-all.sh 1.0.0 web
```

### Using pnpm Scripts

```bash
# Build all packages and apps
pnpm build

# Build individual apps
pnpm build:desktop
pnpm build:mobile
pnpm build:web
pnpm build:packages

# Package installers
pnpm package:desktop    # Creates NSIS, MSI, Portable (Windows), DMG (macOS), AppImage/DEB/Flatpak (Linux)
pnpm package:mobile     # Creates iOS .ipa and Android .aab

# Linting and type checking
pnpm lint
pnpm lint:fix
pnpm typecheck
pnpm typecheck:all

# Testing
pnpm test
pnpm test:desktop
pnpm test:mobile
pnpm test:web
pnpm test:python

# Clean
pnpm clean
pnpm clean:all
```

## Desktop App (Electron)

### Features
- Three-column dashboard layout (Sidebar, Chat, Monitoring)
- Real-time system metrics (CPU, RAM, GPU, Storage)
- Model manager with download progress
- Plugin integrations (GitHub, Web Search, Google Drive, VS Code)
- Tray minimization with auto-start option
- Native installers for all platforms

### Build Outputs
- **Windows**: NSIS installer, MSI installer, Portable executable
- **macOS**: Universal DMG, ZIP (Intel), ZIP (ARM64)
- **Linux**: AppImage, DEB package, Flatpak

### Configuration
Electron Builder config: `apps/desktop/electron-builder.json`

## Mobile App (Capacitor)

### Features
- Native iOS and Android apps
- Bottom navigation bar
- Slide-out sidebar drawer
- Touch-optimized chat interface
- Capacitor plugins (Haptics, Keyboard, Notifications, etc.)

### Build Commands
```bash
cd apps/mobile
pnpm build:ios      # Creates Xcode project
pnpm build:android  # Creates Android App Bundle
```

### Configuration
Capacitor config: `apps/mobile/capacitor.config.ts`

## Web App (Astro)

### Features
- Static SEO-optimized marketing site
- Hero section with animated gradients
- Feature cards with hover effects
- Platform-specific download cards
- Screenshots gallery
- Footer with links and social media
- Sitemap, robots.txt, JSON-LD schema

### Pages
- `/` - Landing page with all sections
- `/docs` - Documentation (to be added)
- `/blog` - Blog (to be added)
- `/changelog` - Release notes

### Deploy
```bash
cd apps/web
pnpm build
# Deploy dist/ to Vercel, Netlify, or any static host
```

## UI Package (@hercule/ui)

Shared React component library with:

### Primitives
- Button, Card, Input, Textarea

### Feedback
- Alert, Toast, Spinner, Progress (Linear & Circular)

### Forms
- Label, Select, Checkbox, Radio, RadioGroup, Switch

### Layout
- Container, Grid, Flex, Stack (HStack/VStack), Divider

### Navigation
- Tabs, Breadcrumbs, Pagination

### Design Tokens
- Colors (semantic, brand, neutral)
- Spacing, Typography, Border Radius
- Shadows, Transitions, Z-Index
- Breakpoints

## Model Management

The desktop app includes a complete model management system:

- **Available Models**: Fetched from Hugging Face (configurable)
- **Quantizations**: q4_k_m, q5_k_m, q8_0
- **Download Progress**: Real-time progress with speed/ETA
- **Model Selection**: Switch between installed models
- **Auto-start**: Configure model to start on app launch
- **Custom Model Directory**: Choose where models are stored

## Plugin System

Extend HERCULE with plugins:

- **GitHub** - Repositories, issues, PRs
- **Web Search** - Real-time search via multiple providers
- **Google Drive** - File access and sync
- **VS Code** - Editor integration
- **Custom Plugins** - TypeScript SDK for building your own

## CI/CD

GitHub Actions workflows:

- **build.yml** - Release builds on tag push
- **dev.yml** - PR checks (lint, typecheck, test)

### Required Secrets
- `GH_TOKEN` - GitHub token for releases
- `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` - Web deployment
- `KEYSTORE_PASSWORD`, `KEYSTORE_ALIAS_PASSWORD` - Android signing
- `DISCORD_WEBHOOK_URL` - Release notifications

## Configuration Files

| File | Purpose |
|------|---------|
| `package.json` | Monorepo root config, workspaces, scripts |
| `pnpm-workspace.yaml` | pnpm workspace config (auto-generated) |
| `tsconfig.json` | TypeScript config with path aliases |
| `turbo.json` | Turborepo pipeline config |
| `apps/desktop/package.json` | Electron app dependencies |
| `apps/desktop/electron-builder.json` | Electron Builder config |
| `apps/mobile/capacitor.config.ts` | Capacitor config |
| `apps/web/astro.config.mjs` | Astro config |
| `apps/web/tailwind.config.mjs` | Tailwind config for web |
| `packages/ui/package.json` | UI library config |

## License

MIT License - see [LICENSE](LICENSE) for details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Support

- GitHub Issues: [github.com/your-org/hercule/issues](https://github.com/your-org/hercule/issues)
- Discussions: [github.com/your-org/hercule/discussions](https://github.com/your-org/hercule/discussions)
- Discord: [discord.gg/hercule](https://discord.gg/hercule)