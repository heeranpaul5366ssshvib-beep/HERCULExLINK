from __future__ import annotations
"""
--------------------------------------------
HERCULE AI Operating System
Module: Plugin UI Panel
--------------------------------------------
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Any, Dict, List, Optional
import threading
import queue


BG = "#0a0e14"
PANEL = "#11161f"
ACCENT = "#00d4ff"
TEXT = "#c9e4f2"
DIM = "#5a6b7c"
GOOD = "#00e676"
WARN = "#ffab40"
BAD = "#ff5252"


class PluginPanel:
    """Plugin management panel for the desktop UI."""

    def __init__(self, parent, controller):
        self.controller = controller
        self.parent = parent
        self.frame = ttk.Frame(parent, style="Panel.TFrame", padding=8)
        self._build()

    def _build(self):
        """Build the plugin management UI."""
        ttk.Label(self.frame, text="PLUGINS", style="Title.TLabel").pack(anchor="w")

        # Notebook for tabs
        self.notebook = ttk.Notebook(self.frame)
        self.notebook.pack(fill="both", expand=True, pady=(8, 0))

        # Tab 1: Installed Plugins
        self.installed_frame = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(self.installed_frame, text="Installed")
        self._build_installed_tab()

        # Tab 2: Available Plugins
        self.available_frame = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(self.available_frame, text="Available")
        self._build_available_tab()

        # Tab 3: Plugin Details
        self.details_frame = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(self.details_frame, text="Details")
        self._build_details_tab()

        # Tab 4: Permissions
        self.permissions_frame = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(self.permissions_frame, text="Permissions")
        self._build_permissions_tab()

        # Tab 5: Configuration
        self.config_frame = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(self.config_frame, text="Configuration")
        self._build_config_tab()

        # Tab 6: Activity/Logs
        self.activity_frame = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(self.activity_frame, text="Activity")
        self._build_activity_tab()

        # Load initial data
        self._refresh_installed()
        self._refresh_available()

    def _build_installed_tab(self):
        """Build the installed plugins tab."""
        # Toolbar
        toolbar = ttk.Frame(self.installed_frame, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="Refresh", command=self._refresh_installed).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Install...", command=self._install_plugin).pack(side="left", padx=2)

        # Treeview for installed plugins
        columns = ("name", "version", "status", "enabled")
        self.installed_tree = ttk.Treeview(self.installed_frame, columns=columns, show="headings", height=15)
        self.installed_tree.heading("name", text="Name")
        self.installed_tree.heading("version", text="Version")
        self.installed_tree.heading("status", text="Status")
        self.installed_tree.heading("enabled", text="Enabled")
        self.installed_tree.column("name", width=200)
        self.installed_tree.column("version", width=80)
        self.installed_tree.column("status", width=100)
        self.installed_tree.column("enabled", width=80)
        self.installed_tree.pack(fill="both", expand=True)
        self.installed_tree.bind("<<TreeviewSelect>>", self._on_installed_select)

        # Action buttons
        actions = ttk.Frame(self.installed_frame, style="Panel.TFrame")
        actions.pack(fill="x", pady=(8, 0))
        self.enable_btn = ttk.Button(actions, text="Enable", command=self._enable_selected, state="disabled")
        self.enable_btn.pack(side="left", padx=2)
        self.disable_btn = ttk.Button(actions, text="Disable", command=self._disable_selected, state="disabled")
        self.disable_btn.pack(side="left", padx=2)
        self.uninstall_btn = ttk.Button(actions, text="Uninstall", command=self._uninstall_selected, state="disabled")
        self.uninstall_btn.pack(side="left", padx=2)
        ttk.Button(actions, text="Details", command=self._show_details).pack(side="left", padx=2)

    def _build_available_tab(self):
        """Build the available plugins tab."""
        toolbar = ttk.Frame(self.available_frame, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="Refresh", command=self._refresh_available).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Install Selected", command=self._install_available_selected).pack(side="left", padx=2)

        columns = ("name", "version", "description", "status")
        self.available_tree = ttk.Treeview(self.available_frame, columns=columns, show="headings", height=15)
        self.available_tree.heading("name", text="Name")
        self.available_tree.heading("version", text="Version")
        self.available_tree.heading("description", text="Description")
        self.available_tree.heading("status", text="Status")
        self.available_tree.column("name", width=150)
        self.available_tree.column("version", width=80)
        self.available_tree.column("description", width=250)
        self.available_tree.column("status", width=100)
        self.available_tree.pack(fill="both", expand=True)

    def _build_details_tab(self):
        """Build the plugin details tab."""
        self.details_text = scrolledtext.ScrolledText(
            self.details_frame,
            bg="#0d1219", fg=TEXT, font=("Consolas", 9),
            state="disabled", wrap="word"
        )
        self.details_text.pack(fill="both", expand=True)

    def _build_permissions_tab(self):
        """Build the permissions tab."""
        toolbar = ttk.Frame(self.permissions_frame, style="Panel.TFrame")
        toolbar.pack(fill="x", pady=(0, 8))
        ttk.Button(toolbar, text="Refresh", command=self._refresh_permissions).pack(side="left", padx=2)

        columns = ("permission", "status")
        self.permissions_tree = ttk.Treeview(self.permissions_frame, columns=columns, show="headings", height=15)
        self.permissions_tree.heading("permission", text="Permission")
        self.permissions_tree.heading("status", text="Status")
        self.permissions_tree.column("permission", width=200)
        self.permissions_tree.column("status", width=150)
        self.permissions_tree.pack(fill="both", expand=True)

        # Action buttons
        perm_actions = ttk.Frame(self.permissions_frame, style="Panel.TFrame")
        perm_actions.pack(fill="x", pady=(8, 0))
        self.approve_btn = ttk.Button(perm_actions, text="Approve", command=self._approve_permission, state="disabled")
        self.approve_btn.pack(side="left", padx=2)
        self.revoke_btn = ttk.Button(perm_actions, text="Revoke", command=self._revoke_permission, state="disabled")
        self.revoke_btn.pack(side="left", padx=2)

    def _build_config_tab(self):
        """Build the configuration tab."""
        self.config_text = scrolledtext.ScrolledText(
            self.config_frame,
            bg="#0d1219", fg=TEXT, font=("Consolas", 9),
            state="normal", wrap="word"
        )
        self.config_text.pack(fill="both", expand=True, pady=(0, 8))

        config_actions = ttk.Frame(self.config_frame, style="Panel.TFrame")
        config_actions.pack(fill="x")
        ttk.Button(config_actions, text="Save", command=self._save_config).pack(side="left", padx=2)
        ttk.Button(config_actions, text="Reload", command=self._reload_config).pack(side="left", padx=2)

    def _build_activity_tab(self):
        """Build the activity/logs tab."""
        self.activity_text = scrolledtext.ScrolledText(
            self.activity_frame,
            bg="#0d1219", fg=TEXT, font=("Consolas", 9),
            state="disabled", wrap="word"
        )
        self.activity_text.pack(fill="both", expand=True)

        activity_actions = ttk.Frame(self.activity_frame, style="Panel.TFrame")
        activity_actions.pack(fill="x", pady=(8, 0))
        ttk.Button(activity_actions, text="Refresh", command=self._refresh_activity).pack(side="left", padx=2)
        ttk.Button(activity_actions, text="Clear", command=self._clear_activity).pack(side="left", padx=2)

    # ============================================================
    # Data Loading
    # ============================================================

    def _refresh_installed(self):
        """Refresh installed plugins list."""
        self.installed_tree.delete(*self.installed_tree.get_children())
        
        # Get plugin manager from controller
        plugin_manager = self._get_plugin_manager()
        if not plugin_manager:
            return

        try:
            plugins = plugin_manager.list_installed()
            for plugin in plugins:
                self.installed_tree.insert("", "end", values=(
                    plugin.get("name", plugin.get("plugin_id", "Unknown")),
                    plugin.get("version", "unknown"),
                    plugin.get("status", "UNKNOWN"),
                    "Yes" if plugin.get("enabled") else "No",
                ), tags=(plugin.get("plugin_id"),))
        except Exception as e:
            self._append_log(f"Error loading installed plugins: {e}")

    def _refresh_available(self):
        """Refresh available plugins list."""
        self.available_tree.delete(*self.available_tree.get_children())
        
        plugin_manager = self._get_plugin_manager()
        if not plugin_manager:
            return

        try:
            plugins = plugin_manager.list_available()
            for plugin in plugins:
                manifest = plugin.get("manifest")
                if manifest:
                    self.available_tree.insert("", "end", values=(
                        manifest.name,
                        manifest.version,
                        manifest.description[:80],
                        "Available" if plugin.get("valid") else "Invalid",
                    ), tags=(manifest.plugin_id,))
        except Exception as e:
            self._append_log(f"Error loading available plugins: {e}")

    def _refresh_permissions(self):
        """Refresh permissions for selected plugin."""
        self.permissions_tree.delete(*self.permissions_tree.get_children())
        
        plugin_id = getattr(self, "_selected_plugin_id", None)
        if not plugin_id:
            return

        plugin_manager = self._get_plugin_manager()
        if not plugin_manager:
            return

        try:
            perms = plugin_manager.get_permissions(plugin_id)
            for perm in perms.get("granted", []):
                self.permissions_tree.insert("", "end", values=(perm, "Granted"), tags=(perm, "granted"))
            for perm in perms.get("pending", []):
                self.permissions_tree.insert("", "end", values=(perm, "Pending Approval"), tags=(perm, "pending"))
            for perm in perms.get("denied", []):
                self.permissions_tree.insert("", "end", values=(perm, "Denied"), tags=(perm, "denied"))

            self.permissions_tree.tag_configure("granted", foreground=GOOD)
            self.permissions_tree.tag_configure("pending", foreground=WARN)
            self.permissions_tree.tag_configure("denied", foreground=BAD)
        except Exception as e:
            self._append_log(f"Error loading permissions: {e}")

    def _refresh_config(self):
        """Refresh configuration for selected plugin."""
        plugin_id = getattr(self, "_selected_plugin_id", None)
        if not plugin_id:
            self.config_text.configure(state="normal")
            self.config_text.delete("1.0", "end")
            self.config_text.insert("1.0", "Select a plugin to edit configuration")
            self.config_text.configure(state="disabled")
            return

        plugin_manager = self._get_plugin_manager()
        if not plugin_manager:
            return

        try:
            config = plugin_manager.registry.get_config(plugin_id)
            manifest = plugin_manager.registry.get_manifest(plugin_id)
            
            self.config_text.configure(state="normal")
            self.config_text.delete("1.0", "end")
            
            if manifest and manifest.configuration_schema:
                # Show schema with current values
                import json
                self.config_text.insert("1.0", json.dumps(config, indent=2))
            else:
                self.config_text.insert("1.0", "# No configuration schema defined for this plugin\n")
                self.config_text.insert("end", json.dumps(config, indent=2))
            self.config_text.configure(state="disabled")
        except Exception as e:
            self._append_log(f"Error loading config: {e}")

    def _refresh_activity(self):
        """Refresh activity log for selected plugin."""
        plugin_id = getattr(self, "_selected_plugin_id", None)
        if not plugin_id:
            self.activity_text.configure(state="normal")
            self.activity_text.delete("1.0", "end")
            self.activity_text.insert("1.0", "Select a plugin to view activity")
            self.config_text.configure(state="disabled")
            return

        plugin_manager = self._get_plugin_manager()
        if not plugin_manager:
            return

        try:
            activity = plugin_manager.registry.get_activity(plugin_id, limit=100)
            self.activity_text.configure(state="normal")
            self.activity_text.delete("1.0", "end")
            if activity:
                for entry in activity:
                    ts = entry.get("timestamp", 0)
                    from datetime import datetime
                    dt = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
                    status = "OK" if entry.get("success") else "FAIL"
                    self.activity_text.insert("end", f"[{dt}] {entry.get('capability', '')} - {status} ({entry.get('duration_ms', 0):.1f}ms)\n")
                    if entry.get("error"):
                        self.activity_text.insert("end", f"  Error: {entry['error']}\n")
            else:
                self.activity_text.insert("1.0", "No activity recorded")
            self.activity_text.configure(state="disabled")
        except Exception as e:
            self._append_log(f"Error loading activity: {e}")

    def _refresh_details(self):
        """Refresh plugin details."""
        plugin_id = getattr(self, "_selected_plugin_id", None)
        if not plugin_id:
            return

        plugin_manager = self._get_plugin_manager()
        if not plugin_manager:
            return

        try:
            plugin = plugin_manager.registry.get(plugin_id)
            manifest = plugin_manager.registry.get_manifest(plugin_id)
            health = plugin_manager.health(plugin_id)

            self.details_text.configure(state="normal")
            self.details_text.delete("1.0", "end")
            
            lines = [
                f"Plugin ID: {plugin_id}",
                f"Name: {manifest.name if manifest else 'Unknown'}",
                f"Version: {manifest.version if manifest else 'Unknown'}",
                f"Author: {manifest.author if manifest else 'Unknown'}",
                f"Description: {manifest.description if manifest else 'N/A'}",
                f"",
                f"Status: {health.get('status', 'Unknown')}",
                f"Enabled: {health.get('enabled', False)}",
                f"Capabilities: {', '.join(health.get('capabilities', [])) or 'None'}",
                f"Permissions: {', '.join(health.get('permissions', [])) or 'None'}",
                f"",
                f"Last Error: {health.get('last_error', 'None')}",
                f"Total Calls: {health.get('total_calls', 0)}",
                f"Last Used: {health.get('last_used', 'Never')}",
            ]
            
            self.details_text.insert("1.0", "\n".join(lines))
            self.details_text.configure(state="disabled")
        except Exception as e:
            self._append_log(f"Error loading details: {e}")

    # ============================================================
    # Event Handlers
    # ============================================================

    def _on_installed_select(self, event):
        """Handle selection in installed tree."""
        selection = self.installed_tree.selection()
        if selection:
            item = self.installed_tree.item(selection[0])
            tags = item.get("tags", ())
            if tags:
                plugin_id = tags[0]
                self._selected_plugin_id = plugin_id
                self.enable_btn.configure(state="normal")
                self.disable_btn.configure(state="normal")
                self.uninstall_btn.configure(state="normal")
                self.approve_btn.configure(state="normal")
                self.revoke_btn.configure(state="normal")
                self._refresh_details()
                self._refresh_permissions()
                self._refresh_config()
                self._refresh_activity()

    def _enable_selected(self):
        """Enable selected plugin."""
        plugin_id = getattr(self, "_selected_plugin_id", None)
        if not plugin_id:
            return
        plugin_manager = self._get_plugin_manager()
        if plugin_manager:
            success, msg = plugin_manager.enable(plugin_id)
            if success:
                messagebox.showinfo("Success", msg)
            else:
                messagebox.showerror("Error", msg)
            self._refresh_installed()

    def _disable_selected(self):
        """Disable selected plugin."""
        plugin_id = getattr(self, "_selected_plugin_id", None)
        if not plugin_id:
            return
        plugin_manager = self._get_plugin_manager()
        if plugin_manager:
            success, msg = plugin_manager.disable(plugin_id)
            if success:
                messagebox.showinfo("Success", msg)
            else:
                messagebox.showerror("Error", msg)
            self._refresh_installed()

    def _uninstall_selected(self):
        """Uninstall selected plugin."""
        plugin_id = getattr(self, "_selected_plugin_id", None)
        if not plugin_id:
            return
        if messagebox.askyesno("Confirm", f"Uninstall plugin {plugin_id}? This cannot be undone."):
            plugin_manager = self._get_plugin_manager()
            if plugin_manager:
                success, msg = plugin_manager.uninstall(plugin_id)
                if success:
                    messagebox.showinfo("Success", msg)
                else:
                    messagebox.showerror("Error", msg)
                self._refresh_installed()
                self._selected_plugin_id = None

    def _install_plugin(self):
        """Install a plugin from file dialog."""
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Select Plugin Directory")
        if path:
            plugin_manager = self._get_plugin_manager()
            if plugin_manager:
                success, msg = plugin_manager.install(path)
                if success:
                    messagebox.showinfo("Success", msg)
                else:
                    messagebox.showerror("Error", msg)
                self._refresh_installed()
                self._refresh_available()

    def _install_available_selected(self):
        """Install selected available plugin."""
        selection = self.available_tree.selection()
        if not selection:
            return
        item = self.available_tree.item(selection[0])
        tags = item.get("tags", ())
        if tags:
            plugin_id = tags[0]
            plugin_manager = self._get_plugin_manager()
            if plugin_manager:
                available = plugin_manager.list_available()
                for p in available:
                    if p.get("manifest") and p["manifest"].plugin_id == plugin_id:
                        success, msg = plugin_manager.install(str(p["source_path"]), plugin_id)
                        if success:
                            messagebox.showinfo("Success", msg)
                        else:
                            messagebox.showerror("Error", msg)
                        self._refresh_installed()
                        self._refresh_available()
                        break

    def _show_details(self):
        """Switch to details tab."""
        self.notebook.select(self.details_frame)

    def _approve_permission(self):
        """Approve selected permission."""
        selection = self.permissions_tree.selection()
        if not selection:
            return
        item = self.permissions_tree.item(selection[0])
        perm = item.get("values", [None])[0]
        plugin_id = getattr(self, "_selected_plugin_id", None)
        if plugin_id and perm:
            plugin_manager = self._get_plugin_manager()
            if plugin_manager:
                if plugin_manager.approve_permission(plugin_id, perm):
                    messagebox.showinfo("Success", f"Permission {perm} approved")
                else:
                    messagebox.showerror("Error", "Failed to approve permission")
                self._refresh_permissions()

    def _revoke_permission(self):
        """Revoke selected permission."""
        selection = self.permissions_tree.selection()
        if not selection:
            return
        item = self.permissions_tree.item(selection[0])
        perm = item.get("values", [None])[0]
        plugin_id = getattr(self, "_selected_plugin_id", None)
        if plugin_id and perm:
            if messagebox.askyesno("Confirm", f"Revoke permission {perm}?"):
                plugin_manager = self._get_plugin_manager()
                if plugin_manager:
                    if plugin_manager.revoke_permission(plugin_id, perm):
                        messagebox.showinfo("Success", f"Permission {perm} revoked")
                    else:
                        messagebox.showerror("Error", "Failed to revoke permission")
                    self._refresh_permissions()

    def _save_config(self):
        """Save plugin configuration."""
        plugin_id = getattr(self, "_selected_plugin_id", None)
        if not plugin_id:
            return
        try:
            config_text = self.config_text.get("1.0", "end-1c")
            config = json.loads(config_text)
            plugin_manager = self._get_plugin_manager()
            if plugin_manager:
                success, msg = plugin_manager.update_config(plugin_id, config)
                if success:
                    messagebox.showinfo("Success", msg)
                else:
                    messagebox.showerror("Error", msg)
        except json.JSONDecodeError:
            messagebox.showerror("Error", "Invalid JSON")

    def _reload_config(self):
        """Reload configuration from disk."""
        self._refresh_config()

    def _clear_activity(self):
        """Clear activity log display."""
        self.activity_text.configure(state="normal")
        self.activity_text.delete("1.0", "end")
        self.activity_text.configure(state="disabled")

    # ============================================================
    # Helpers
    # ============================================================

    def _get_plugin_manager(self):
        """Get plugin manager from controller services."""
        services = getattr(self.controller, "services", {})
        return services.get("plugins")

    def _append_log(self, msg: str):
        """Append to event stream."""
        if hasattr(self.controller, "_append_chat"):
            self.controller._append_chat(f"[Plugins] {msg}")