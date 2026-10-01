# Plugin SDK Architecture Inspection Report

## Overview

Inspection of the `plugin_sdk/` module and integration points with HERCULE core. The SDK provides a complete plugin platform with manifest validation, lifecycle management, permission enforcement, isolation, and UI management.

---

## Discovered Interfaces

### 1. PluginManifest (`plugin_sdk/manifest.py`)

**Purpose**: Complete metadata schema for plugins.

**Key Fields**:
- `plugin_id`: Unique identifier (e.g., "example.web_research")
- `name`, `version`, `description`, `author`, `homepage`
- `min_hercule_version`, `max_hercule_version`: Version constraints
- `entrypoint`: Python module/class entrypoint (default: "Plugin")
- `capabilities`: List of declared capabilities (from `PluginCapability` enum)
- `permissions`: List of required permissions (from `PluginPermission` enum)
- `dependencies`: Other plugin IDs required
- `configuration_schema`: JSON Schema for config validation
- `plugin_api_version`: Plugin API version (default: "1.0")
- `icon`, `tags`: Optional metadata

**Validation**: `validate()` method checks required fields, unknown permissions/capabilities

**Permissions Enum** (12 total):
- Non-sensitive (auto-granted): `filesystem_read`, `network`, `system_info`, `browser`, `clipboard`
- Sensitive (require approval): `shell`, `process_execution`, `filesystem_write`, `secrets`, `microphone`, `camera`, `automation`

**Capabilities Enum** (11 total): `search`, `research`, `summarize`, `code_generation`, `file_operations`, `terminal`, `browser_automation`, `data_analysis`, `image_processing`, `audio_processing`, `custom`

---

### 2. Plugin Base Class (`plugin_sdk/plugin.py`)

**Plugin**: Abstract base class with full lifecycle hooks.

**Lifecycle Methods** (override in subclasses):
- `on_discover()` → `bool`: Called during discovery
- `on_validate(hercule_version)` → `bool`: Version compatibility check
- `on_install()` → `bool`: Installation setup
- `on_enable()` → `bool`: Enable (register tools, subscribe events)
- `on_disable()` → `bool`: Disable (cleanup)
- `on_uninstall()` → `bool`: Uninstall cleanup
- `on_reload()` → `bool`: Reload handling
- `on_startup()`: HERCULE startup (if enabled)
- `on_shutdown()`: HERCULE shutdown
- `health()` → `Dict`: Health information
- `execute()`: Abstract method (legacy compatibility)

**Status Tracking**: `PluginStatus` enum (10 states: DISCOVERED, VALIDATED, INSTALLED, DISABLED, ENABLED, RUNNING, INVALID, INCOMPATIBLE, FAILED)

**Context Injection**: `set_context(PluginContext)` provides controlled API access

---

### 3. PluginContext (`plugin_sdk/plugin.py`)

**Purpose**: The ONLY interface plugins have to HERCULE internals. Every operation passes through policy layer.

**Properties**:
- `plugin_id`: Read-only plugin identifier
- `logger`: Scoped logger (`HERCULE.Plugin.{plugin_id}`)
- `config`: Isolated configuration dict (copy-on-read)
- `events`: `PluginEventBus` - controlled event system
- `tools`: `PluginToolRegistry` - tool registration via AbilityManager
- `memory`: `PluginMemoryAccess` - scoped key-value + search
- `permissions`: `PluginPermissionChecker` - runtime permission validation
- `workspace`: `PluginWorkspaceAccess` - restricted filesystem
- `ui_hooks`: `PluginUIHooks` - UI panel registration
- `model_access`: `PluginModelAccess` - ModelRouter proxy (optional)

**Critical Security**: Plugins NEVER get direct access to:
- Brain, Orchestrator, ModelManager, MemoryManager
- Other plugins' data
- Global HERCULE configuration
- Internal managers

---

### 4. PluginEventBus (`plugin_sdk/plugin.py` + `plugin_sdk/events.py`)

**Plugin-to-Core Subscriptions** (ALLOWED_SUBSCRIPTIONS):
- `on_startup`, `on_shutdown`
- `on_task_created`, `on_task_completed`, `on_task_failed`
- `on_tool_result`, `on_memory_update`
- `on_project_open`, `on_project_close`

**Plugin-to-Core Emissions** (ALLOWED_EMISSIONS):
- `on_plugin_enabled`, `on_plugin_disabled`

**CorePluginEventBus** (`events.py`): Dispatches core events to enabled plugins only.

**Security**: Plugins cannot subscribe/emit unauthorized events. Disallowed attempts are logged and rejected.

---

### 5. PluginToolRegistry (`plugin_sdk/plugin.py`)

**Purpose**: Register plugin tools through AbilityManager.

**register_tool(name, description, handler, permissions, capability)**:
- Creates dynamic `Ability` subclass
- Registers with `AbilityManager`
- Tool name: `{plugin_id}.{name}`
- Execution goes through normal HERCULE pipeline:
  `Brain → ModelRouter → Tool Matcher → PolicyManager → Plugin Tool → Verification`

**unregister_tool(name)**: Removes from AbilityManager

---

### 6. PluginMemoryAccess (`plugin_sdk/plugin.py`)

**Scoped Memory Operations**:
- `store(key, value)`: Keys scoped to `plugin.{plugin_id}.{key}`
- `retrieve(key)`: Scoped retrieval
- `search(query, limit)`: Scoped search

**Isolation**: Plugins cannot access other plugins' memory namespace.

---

### 7. PluginPermissionChecker (`plugin_sdk/plugin.py` + `plugin_sdk/permissions.py`)

**Runtime Permission Enforcement**:
- `has(permission)` → `bool`: Check if granted
- `check(permission)` → `bool`: Enforce (raises `PermissionError`)
- `get_granted()`: List granted permissions
- `get_declared()`: List declared in manifest
- `get_pending()`: List pending sensitive permissions

**Behavior**:
- Non-declared permissions raise `PermissionError`
- Non-sensitive permissions auto-granted at enable time
- Sensitive permissions require explicit approval (checked via `PluginPermissionModel`)

---

### 8. PluginWorkspaceAccess (`plugin_sdk/plugin.py`)

**Restricted Filesystem**:
- Base path: `data/plugins/workspace/{plugin_id}/`
- `read_file(path)`: Requires `filesystem_read`
- `write_file(path, content)`: Requires `filesystem_write`
- `list_files(path)`: Requires `filesystem_read`

**Isolation**: Plugins cannot escape their workspace directory.

---

### 9. PluginUIHooks (`plugin_sdk/plugin.py`)

**UI Panel Registration**:
- `register_panel(panel_id, title, component, position)`
- `unregister_panel(panel_id)`
- `get_panels()`: Returns registered panels

---

### 10. PluginModelAccess (`plugin_sdk/model_access.py`)

**ModelRouter Proxy**:
- `request(task, purpose, preferred_model, context)`: Routes through ModelRouter
- `list_available_models()`: Read-only model discovery
- `get_router_health()`: Router status

**Permission Required**: `network` (checked at request time)

**Security**: Cannot bypass model routing, provider selection, or health checks. Cannot instantiate arbitrary model providers.

---

### 11. PluginPermissionModel (`plugin_sdk/permissions.py`)

**Approval System**:
- Approvals tied to `plugin_id + plugin_version`
- `PermissionApproval` records: status (PENDING, GRANTED, DENIED, REVOKED), timestamps
- Persisted to `config/plugin_approvals.json`

**Version Invalidation**: `check_permission_set_changed()` revokes ALL old sensitive approvals on version change

**Key Methods**:
- `is_sensitive(permission)`: Check if requires approval
- `is_granted(plugin_id, version, permission)`: Check grant status
- `request_approval()`, `grant_approval()`, `deny_approval()`, `revoke_approval()`
- `check_permission_set_changed()`: Update safety check

---

### 12. PluginLoader (`plugin_sdk/plugin_loader.py`)

**Discovery**: Scans `plugins/` dir for directories with `manifest.json` or `.zip` packages

**Validation**: Manifest schema + version compatibility (using `packaging.version`)

**Installation**: Copies to `data/plugins/installed/{plugin_id}/`

**Loading**: Dynamic import, finds Plugin subclass, instantiates

**Uninstall**: Removes installed directory

---

### 13. PluginRegistry (`plugin_sdk/plugin_registry.py`)

**Registry with Lifecycle Tracking**:
- Thread-safe plugin/manifest/config storage
- Per-plugin config persistence: `config/plugins/{plugin_id}.json`
- Activity logging (audit trail): timestamp, plugin_id, capability, permission, success, duration_ms, error
- Max 1000 activity entries

---

### 14. PluginManager (`plugin_sdk/plugin_manager.py`)

**Full Lifecycle Orchestration**:

| Operation | Description |
|-----------|-------------|
| `discover()` | Find available plugins |
| `validate()` | Check manifest + compatibility |
| `install()` | Install from local path |
| `enable()` | Create context, check permissions, call `on_enable`, register tools |
| `disable()` | Unregister tools, call `on_disable`, cleanup context |
| `uninstall()` | Disable + remove from disk + remove config |
| `reload()` | Disable → reload from disk → enable |
| `health()` | Get plugin health info |
| `all_health()` | Health for all plugins |
| `get_permissions()` | View granted/pending/denied |
| `approve_permission()` | Grant sensitive permission |
| `revoke_permission()` | Revoke permission |
| `update_config()` | Update plugin configuration |
| `check_compatibility()` | Version compatibility check |
| `check_update_permissions()` | Compare old vs new manifest permissions |
| `update_plugin()` | Safe update with permission comparison |
| `list_installed()` | Installed plugins with status |
| `list_available()` | Available plugins for installation |

**Context Creation** (`_create_context`): Injects all controlled interfaces

**Tool Registration/Unregistration**: Called during enable/disable

---

### 15. PluginPanel (`plugin_sdk/ui_panel.py`)

**6-Tab Desktop UI**:
1. **Installed**: List, enable/disable/uninstall, install from dir
2. **Available**: Discover local plugins, install selected
3. **Details**: Full plugin info, health, capabilities
4. **Permissions**: Granted/pending/denied with approve/revoke buttons
5. **Configuration**: JSON editor with schema validation
6. **Activity**: Audit log with timestamps

**Integration**: Added to desktop app left sidebar (row 12)

---

## Existing Extension Points

### HERCULE Runtime Initialization (`runtime/initializer.py`)

PluginManager created with references to:
- `AbilityManager` → tool registration
- `MemoryManager` → scoped memory access
- `ModelManager`/`ModelRouter` → model access
- `SecurityManager` → permission enforcement
- Core event bus → event dispatch

### Desktop UI (`interface/desktop_app.py`)

PluginPanel integrated into left sidebar. Requires `PLUGIN_PANEL_AVAILABLE` flag.

### CLI (`boot.py`)

Plugins available through normal `HerculeCli` routing.

---

## Security Boundaries

### 1. Permission Independence
- Having `NETWORK` does NOT grant `SHELL` or `FILESYSTEM_WRITE`
- Each permission checked independently
- Verified by `test_permission_independence` test

### 2. Fail-Closed Behavior
- Every denied operation raises `PermissionError`
- No silent failures or fallbacks
- Non-declared permissions rejected

### 3. Version-Bound Approvals
- Approvals tied to `plugin_id@version`
- Version change invalidates ALL previous sensitive approvals
- New permissions in updates require new approvals

### 4. Isolation Layers
- **Filesystem**: Workspace-scoped (`data/plugins/workspace/{plugin_id}/`)
- **Memory**: Key-scoped (`plugin.{plugin_id}.{key}`)
- **Config**: Per-plugin files (`config/plugins/{plugin_id}.json`)
- **API Surface**: PluginContext only exposes controlled interfaces

### 5. Model Access Control
- Only via `ModelRouter` proxy
- Requires `network` permission
- Cannot bypass routing/health checks

### 6. Tool Registration
- Dynamic abilities registered with `AbilityManager`
- Execution through normal HERCULE pipeline with policy checks
- Disabled/uninstalled plugins have tools removed

### 7. Event System
- Controlled subscriptions/emissions
- Disallowed events rejected and logged
- Core dispatches only to RUNNING plugins

---

## Compatibility Constraints

### Version Compatibility
- `min_hercule_version` / `max_hercule_version` in manifest
- `plugin_api_version` (currently "1.0")
- Validation uses `packaging.version` for semantic comparison

### Package Format
- Directory with `manifest.json` + `plugin.py` (entrypoint)
- ZIP package with same structure
- No support for wheel/pip packages yet

### Python Dependencies
- No isolated dependency management
- Plugins share HERCULE's Python environment
- `requirements.txt` in plugin dir not automatically installed

---

## Potential Weaknesses Found

### 1. ZIP Path Traversal (CHECKPOINT 12)
`_install_from_package()` uses `zf.extractall(target_dir)` without validating archive member paths. Malicious entries like `../evil.txt` or absolute paths could escape installation directory.

### 2. PluginPermissionChecker in plugin.py vs permissions.py
Two different `PluginPermissionChecker` classes exist:
- `plugin_sdk/plugin.py:206` - Simple version (granted_permissions list)
- `plugin_sdk/permissions.py:230` - Full version (uses PluginPermissionModel)

The PluginManager uses the full version from permissions.py, but the PluginContext in plugin.py defines a simpler one. This could cause confusion.

### 3. No Package Signature Verification
ZIP packages not cryptographically verified. Any ZIP with valid manifest can be installed.

### 4. No Dependency Resolution
`dependencies` field in manifest not enforced during install/enable.

### 5. No Resource Limits
Plugins can consume unbounded CPU/memory. No sandboxing (same process).

### 6. ModelRouter Health Check Not Cached
`PluginModelAccess.get_router_health()` calls router.health() each time.

### 7. Activity Log Not Persisted
Activity log only in memory (`PluginRegistry._activity_log`). Lost on restart.

### 8. Config Schema Validation Basic
`update_config()` only checks `type` field via `eval()`. No validation of `minimum`, `maximum`, `enum`, etc.

### 9. PluginEventBus in plugin.py vs events.py
Two implementations exist. The one in plugin.py is simpler and used by PluginContext. The one in events.py has `CorePluginEventBus` and stricter ALLOWED_SUBSCRIPTIONS/EMISSIONS. The PluginManager creates the events.py version.

### 10. No Plugin-to-Plugin Communication
Plugins cannot directly communicate. Must go through core events or shared memory (but memory is isolated).

---

## Conclusion

**CHECKPOINT 1 GATE: PASS**

- Existing API is well-understood
- No architectural blocker identified
- Implementation can proceed using existing interfaces
- 10 potential weaknesses documented for targeted testing in later checkpoints