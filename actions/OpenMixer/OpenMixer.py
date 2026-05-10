from src.backend.PluginManager.ActionBase import ActionBase
from loguru import logger as log
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio
import globals as gl
import os
import json
import zipfile
import shutil
import tempfile

ROW_OPTIONS = ["Custom Text"]
ROW_KEYS    = ["custom"]

DEFAULTS = {
    "custom_icon_path": "",
    "top_content":    "custom",
    "center_content": "custom",
    "bottom_content": "custom",
    "custom_top":    "",
    "custom_center": "Mixer",
    "custom_bottom": "",
}


class OpenMixer(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_ready(self):
        self.plugin_base.register_action(self)
        # Write defaults for any missing keys so settings are always initialized
        s = self.get_settings()
        changed = False
        for k, v in DEFAULTS.items():
            if k not in s:
                s[k] = v
                changed = True
        if changed:
            self.set_settings(s)
        self._update_display()

    def on_removed(self):
        self.plugin_base.unregister_action(self)

    def on_key_down(self):
        self._load_page(self.plugin_base.mixer_page_path())

    def _load_page(self, path: str):
        if not path or not os.path.exists(path):
            return
        try:
            page = gl.page_manager.get_page(path, deck_controller=self.deck_controller)
        except TypeError:
            try:
                page = gl.page_manager.get_page(path)
            except Exception:
                return
        except Exception:
            return
        if page is not None:
            self.deck_controller.load_page(page)

    def on_sinks_updated(self):
        self._update_display()

    def _resolve_label(self, content_key, custom_key) -> str:
        s = self.get_settings()
        mode = s.get(content_key, DEFAULTS[content_key])
        return s.get(custom_key, DEFAULTS.get(custom_key, ""))

    def _update_display(self):
        s = self.get_settings()
        custom_icon = s.get("custom_icon_path", "").strip()
        if custom_icon and os.path.exists(custom_icon):
            self.set_media(media_path=custom_icon, size=0.75)
        else:
            default = os.path.join(self.plugin_base.PATH, "assets", "open_mixer.png")
            self.set_media(media_path=default if os.path.exists(default) else None, size=0.75)
        self.set_top_label(self._resolve_label("top_content", "custom_top"))
        self.set_center_label(self._resolve_label("center_content", "custom_center"))
        self.set_bottom_label(self._resolve_label("bottom_content", "custom_bottom"))

    def get_config_rows(self) -> list:
        rows = []

        self.icon_entry = Adw.EntryRow()
        self.icon_entry.set_title("Custom Icon (PNG, SVG, GIF)")
        browse_btn = Gtk.Button(label="Browse…")
        browse_btn.set_valign(Gtk.Align.CENTER)
        browse_btn.add_css_class("flat")
        browse_btn.connect("clicked", self._on_browse)
        self.icon_entry.add_suffix(browse_btn)
        rows.append(self.icon_entry)

        self.top_combo, self.top_entry = self._make_label_row("Top Label", rows)
        self.center_combo, self.center_entry = self._make_label_row("Center Label", rows)
        self.bottom_combo, self.bottom_entry = self._make_label_row("Bottom Label", rows)

        # ── Export / Import ───────────────────────────────────────────────
        sep = Gtk.Separator()
        sep.set_margin_top(12)
        sep.set_margin_bottom(4)
        rows.append(sep)

        lbl = Gtk.Label(label="<b>Plugin Settings</b>")
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_margin_start(6)
        rows.append(lbl)

        hint = Gtk.Label(label="Export or import all plugin settings (priority list, hidden apps, custom icons).")
        hint.set_halign(Gtk.Align.START)
        hint.set_wrap(True)
        hint.set_margin_start(6)
        rows.append(hint)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_margin_top(6)

        export_btn = Gtk.Button(label="Export Settings…")
        export_btn.add_css_class("suggested-action")
        export_btn.connect("clicked", self._on_export)

        import_btn = Gtk.Button(label="Import Settings…")
        import_btn.connect("clicked", self._on_import)

        btn_box.append(export_btn)
        btn_box.append(import_btn)
        rows.append(btn_box)

        self._load_config_values()
        self._connect_signals()
        return rows

    def _make_label_row(self, title, rows):
        combo = Adw.ComboRow()
        combo.set_title(title)
        combo.set_model(Gtk.StringList.new(ROW_OPTIONS))
        rows.append(combo)
        entry = Adw.EntryRow()
        entry.set_title(f"{title}: Custom Text")
        rows.append(entry)
        return combo, entry

    def _load_config_values(self):
        s = self.get_settings()
        self.icon_entry.set_text(s.get("custom_icon_path", ""))

        def load_combo(combo, entry, ck, cust):
            mode = s.get(ck, DEFAULTS[ck])
            combo.set_selected(ROW_KEYS.index(mode) if mode in ROW_KEYS else 0)
            entry.set_text(s.get(cust, DEFAULTS.get(cust, "")))
            entry.set_sensitive(mode == "custom")

        load_combo(self.top_combo,    self.top_entry,    "top_content",    "custom_top")
        load_combo(self.center_combo, self.center_entry, "center_content", "custom_center")
        load_combo(self.bottom_combo, self.bottom_entry, "bottom_content", "custom_bottom")

    def _connect_signals(self):
        self.icon_entry.connect("changed", self._on_changed)
        for combo, entry in [(self.top_combo, self.top_entry),
                             (self.center_combo, self.center_entry),
                             (self.bottom_combo, self.bottom_entry)]:
            combo.connect("notify::selected", lambda w, _, e=entry: (
                e.set_visible(ROW_KEYS[w.get_selected()] == "custom") or
                e.set_sensitive(ROW_KEYS[w.get_selected()] == "custom"),
                self._on_changed()
            ))
            entry.connect("changed", self._on_changed)

    def _on_changed(self, *args):
        settings = self.get_settings()
        settings["custom_icon_path"] = self.icon_entry.get_text()
        settings["top_content"]      = ROW_KEYS[self.top_combo.get_selected()]
        settings["center_content"]   = ROW_KEYS[self.center_combo.get_selected()]
        settings["bottom_content"]   = ROW_KEYS[self.bottom_combo.get_selected()]
        settings["custom_top"]       = self.top_entry.get_text()
        settings["custom_center"]    = self.center_entry.get_text()
        settings["custom_bottom"]    = self.bottom_entry.get_text()
        self.set_settings(settings)
        self._update_display()

    def _get_parent_window(self):
        widget = self.icon_entry
        while widget:
            if isinstance(widget, Gtk.Window):
                return widget
            widget = widget.get_parent()
        return None

    def _on_export(self, _):
        parent = self._get_parent_window()
        fd = Gtk.FileDialog()
        fd.set_title("Export VolumeMixer Settings")
        fd.set_initial_name("volumemixer_backup.zip")

        f = Gtk.FileFilter()
        f.set_name("ZIP files")
        f.add_mime_type("application/zip")
        f.add_pattern("*.zip")
        fall = Gtk.FileFilter()
        fall.set_name("All files")
        fall.add_pattern("*")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(f)
        filters.append(fall)
        fd.set_filters(filters)
        fd.set_default_filter(f)

        def on_done(d, result):
            try:
                file = d.save_finish(result)
                if not file:
                    return
                zip_path = file.get_path()
                plugin_dir = self.plugin_base.PATH
                pages_dir = os.path.join(
                    os.path.expanduser("~"),
                    ".var", "app", "com.core447.StreamController", "data", "pages"
                )

                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                    # Plugin settings (priority list, hidden list, custom icons)
                    ps_path = os.path.join(plugin_dir, "plugin_settings.json")
                    if os.path.exists(ps_path):
                        zf.write(ps_path, "plugin_settings.json")

                    # Bundled mixer page
                    mixer_page = os.path.join(plugin_dir, "pages", "BetterVolumeMixer.json")
                    if os.path.exists(mixer_page):
                        zf.write(mixer_page, "pages/BetterVolumeMixer.json")

                    # All user pages (Main + any others that might reference our actions)
                    if os.path.exists(pages_dir):
                        for fn in os.listdir(pages_dir):
                            if fn.endswith(".json"):
                                zf.write(os.path.join(pages_dir, fn), f"user_pages/{fn}")

                self._show_toast(f"Exported to {os.path.basename(zip_path)}")
            except Exception as e:
                self._show_toast(f"Export failed: {e}")

        fd.save(parent, None, on_done)

    def _on_import(self, _):
        parent = self._get_parent_window()

        # Confirm before overwriting
        confirm = Adw.MessageDialog(
            transient_for=parent,
            modal=True,
            heading="Import Settings",
            body="This will overwrite your current plugin settings and pages. Are you sure?",
        )
        confirm.add_response("cancel", "Cancel")
        confirm.add_response("import", "Import")
        confirm.set_response_appearance("import", Adw.ResponseAppearance.DESTRUCTIVE)
        confirm.set_default_response("cancel")

        def on_confirm(d, response):
            d.destroy()
            if response != "import":
                return
            self._open_import_picker(parent)

        confirm.connect("response", on_confirm)
        confirm.present()

    def _open_import_picker(self, parent):
        fd = Gtk.FileDialog()
        fd.set_title("Import VolumeMixer Settings")

        f = Gtk.FileFilter()
        f.set_name("ZIP files")
        f.add_mime_type("application/zip")
        f.add_pattern("*.zip")
        fall = Gtk.FileFilter()
        fall.set_name("All files")
        fall.add_pattern("*")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(f)
        filters.append(fall)
        fd.set_filters(filters)
        fd.set_default_filter(f)

        def on_done(d, result):
            try:
                file = d.open_finish(result)
                if not file:
                    return
                zip_path = file.get_path()
                plugin_dir = self.plugin_base.PATH
                pages_dir = os.path.join(
                    os.path.expanduser("~"),
                    ".var", "app", "com.core447.StreamController", "data", "pages"
                )

                with zipfile.ZipFile(zip_path, "r") as zf:
                    names = zf.namelist()

                    # Restore plugin_settings.json
                    if "plugin_settings.json" in names:
                        with zf.open("plugin_settings.json") as f:
                            ps = json.load(f)
                        if "priority_list" in ps:
                            self.plugin_base.set_priority_list(ps["priority_list"])
                        if "hidden_list" in ps:
                            self.plugin_base.set_hidden_list(ps["hidden_list"])
                        if "custom_icons" in ps:
                            self.plugin_base.set_custom_icons(ps["custom_icons"])

                    # Restore bundled mixer page
                    if "pages/BetterVolumeMixer.json" in names:
                        dest = os.path.join(plugin_dir, "pages", "BetterVolumeMixer.json")
                        with zf.open("pages/BetterVolumeMixer.json") as f:
                            data = f.read()
                        with open(dest, "wb") as out:
                            out.write(data)

                    # Restore user pages
                    os.makedirs(pages_dir, exist_ok=True)
                    for name in names:
                        if name.startswith("user_pages/") and name.endswith(".json"):
                            fn = os.path.basename(name)
                            dest = os.path.join(pages_dir, fn)
                            with zf.open(name) as f:
                                data = f.read()
                            with open(dest, "wb") as out:
                                out.write(data)

                self.plugin_base._refresh_sinks()
                self._show_toast("Import successful — please restart StreamController")
            except Exception as e:
                self._show_toast(f"Import failed: {e}")

        fd.open(parent, None, on_done)

    def _show_toast(self, message: str):
        """Show a brief confirmation dialog."""
        parent = self._get_parent_window()
        dialog = Adw.MessageDialog(
            transient_for=parent,
            modal=True,
            heading=message,
        )
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.connect("response", lambda d, _: d.destroy())
        dialog.present()

    def _on_browse(self, _):
        parent = self._get_parent_window()
        fd = Gtk.FileDialog()
        fd.set_title("Select Icon File")
        f = Gtk.FileFilter()
        f.set_name("Image files")
        for m in ("image/png", "image/svg+xml", "image/gif"):
            f.add_mime_type(m)
        fall = Gtk.FileFilter()
        fall.set_name("All files")
        fall.add_pattern("*")
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(f)
        filters.append(fall)
        fd.set_filters(filters)
        fd.set_default_filter(f)
        def on_done(d, result):
            try:
                file = d.open_finish(result)
                if file:
                    self.icon_entry.set_text(file.get_path())
            except Exception:
                pass
        fd.open(parent, None, on_done)
