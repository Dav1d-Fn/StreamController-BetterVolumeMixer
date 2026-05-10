from src.backend.PluginManager.ActionBase import ActionBase
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio
import os


# Row content options for volume buttons
ROW_OPTIONS = ["Volume %", "App Name", "Custom Text"]
ROW_KEYS    = ["volume", "appname", "custom"]

DEFAULTS = {
    "slot_index": 0,
    "volume_step": 5,
    "show_volume": False,
    "custom_icon_path": "",
    "top_content":    "custom",
    "center_content": "custom",
    "bottom_content": "custom",
    "custom_top":    "",
    "custom_center": "▲",
    "custom_bottom": "",
    "sync_settings": True,
}


class VolumeUp(ActionBase):
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
        s = self.get_settings()
        step = s.get("volume_step", 5) / 100.0
        slot = s.get("slot_index", 0)
        self.plugin_base.change_volume(slot, step)

    def on_sinks_updated(self):
        self._update_display()

    def _resolve_label(self, content_key: str, custom_key: str, slot: int) -> str:
        s = self.get_settings()
        mode = s.get(content_key, DEFAULTS[content_key])
        if mode == "volume":
            vol = self.plugin_base.get_volume(slot)
            return f"{vol}%" if vol is not None else ""
        elif mode == "appname":
            sink = self.plugin_base.get_sink_for_slot(slot)
            return self.plugin_base._app_name(sink)[:10] if sink else ""
        return s.get(custom_key, "")

    def _update_display(self):
        s = self.get_settings()
        slot = s.get("slot_index", 0)
        custom_icon = s.get("custom_icon_path", "").strip()

        # Icon
        if custom_icon and os.path.exists(custom_icon):
            self.set_media(media_path=custom_icon, size=0.75)
        else:
            default = os.path.join(self.plugin_base.PATH, "assets", "volume_up.png")
            self.set_media(media_path=default if os.path.exists(default) else None, size=0.75)

        self.set_top_label(self._resolve_label("top_content", "custom_top", slot))
        self.set_center_label(self._resolve_label("center_content", "custom_center", slot))
        self.set_bottom_label(self._resolve_label("bottom_content", "custom_bottom", slot))

    def get_config_rows(self) -> list:
        rows = []

        # ── Slot + Step ───────────────────────────────────────────────────
        self.slot_spinner = Adw.SpinRow.new_with_range(0, 3, 1)
        self.slot_spinner.set_title("Column Slot (0–3)")

        self.step_spinner = Adw.SpinRow.new_with_range(1, 20, 1)
        self.step_spinner.set_title("Volume Step (%)")

        self.sync_row = Adw.SwitchRow()
        self.sync_row.set_title("Sync settings to all Volume Up buttons")
        self.sync_row.set_subtitle("Changes here apply to all Volume Up actions")

        rows += [self.slot_spinner, self.step_spinner, self.sync_row]

        # ── Icon ──────────────────────────────────────────────────────────
        self.icon_entry = Adw.EntryRow()
        self.icon_entry.set_title("Custom Icon (PNG, SVG, GIF)")
        browse_btn = Gtk.Button(label="Browse…")
        browse_btn.set_valign(Gtk.Align.CENTER)
        browse_btn.add_css_class("flat")
        browse_btn.connect("clicked", self._on_browse)
        self.icon_entry.add_suffix(browse_btn)
        rows.append(self.icon_entry)

        # ── Label rows ────────────────────────────────────────────────────
        self.top_combo, self.top_entry = self._make_label_row("Top Label", rows)
        self.center_combo, self.center_entry = self._make_label_row("Center Label", rows)
        self.bottom_combo, self.bottom_entry = self._make_label_row("Bottom Label", rows)

        self._load_config_values()
        self._connect_signals()
        return rows

    def _make_label_row(self, title: str, rows: list):
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
        self.slot_spinner.set_value(s.get("slot_index", DEFAULTS["slot_index"]))
        self.step_spinner.set_value(s.get("volume_step", DEFAULTS["volume_step"]))
        self.sync_row.set_active(s.get("sync_settings", DEFAULTS["sync_settings"]))
        self.icon_entry.set_text(s.get("custom_icon_path", ""))

        def load_combo(combo, entry, content_key, custom_key):
            mode = s.get(content_key, DEFAULTS[content_key])
            idx = ROW_KEYS.index(mode) if mode in ROW_KEYS else 0
            combo.set_selected(idx)
            entry.set_text(s.get(custom_key, DEFAULTS.get(custom_key, "")))
            # set_visible must be called after set_selected to work on first open
            entry.set_sensitive(mode == "custom")
            entry.set_sensitive(mode == "custom")

        load_combo(self.top_combo, self.top_entry, "top_content", "custom_top")
        load_combo(self.center_combo, self.center_entry, "center_content", "custom_center")
        load_combo(self.bottom_combo, self.bottom_entry, "bottom_content", "custom_bottom")

    def _connect_signals(self):
        self.slot_spinner.connect("changed", self._on_changed)
        self.step_spinner.connect("changed", self._on_changed)
        self.sync_row.connect("notify::active", self._on_changed)
        self.icon_entry.connect("changed", self._on_changed)

        for combo, entry, ck, cust in [
            (self.top_combo,    self.top_entry,    "top_content",    "custom_top"),
            (self.center_combo, self.center_entry, "center_content", "custom_center"),
            (self.bottom_combo, self.bottom_entry, "bottom_content", "custom_bottom"),
        ]:
            combo.connect("notify::selected", lambda w, _, e=entry, c=ck: (
                e.set_sensitive(ROW_KEYS[w.get_selected()] == "custom"),
                self._on_changed()
            ))
            entry.connect("changed", self._on_changed)

    def _on_changed(self, *args):
        settings = self.get_settings()
        settings["slot_index"]      = int(self.slot_spinner.get_value())
        settings["volume_step"]     = int(self.step_spinner.get_value())
        settings["sync_settings"]   = self.sync_row.get_active()
        settings["custom_icon_path"]= self.icon_entry.get_text()
        settings["top_content"]     = ROW_KEYS[self.top_combo.get_selected()]
        settings["center_content"]  = ROW_KEYS[self.center_combo.get_selected()]
        settings["bottom_content"]  = ROW_KEYS[self.bottom_combo.get_selected()]
        settings["custom_top"]      = self.top_entry.get_text()
        settings["custom_center"]   = self.center_entry.get_text()
        settings["custom_bottom"]   = self.bottom_entry.get_text()
        self.set_settings(settings)

        # Sync to other VolumeUp actions if enabled
        if settings["sync_settings"]:
            self._sync_to_siblings(settings)

        self._update_display()

    def _sync_to_siblings(self, settings: dict):
        """Copy non-slot settings to all other VolumeUp actions."""
        sync_keys = ["volume_step", "sync_settings", "custom_icon_path",
                     "top_content", "center_content", "bottom_content",
                     "custom_top", "custom_center", "custom_bottom"]
        for action in self.plugin_base._registered_actions:
            if action is self or type(action).__name__ != "VolumeUp":
                continue
            try:
                s = action.get_settings()
                for k in sync_keys:
                    s[k] = settings[k]
                action.set_settings(s)
                action._update_display()
            except Exception:
                pass

    def _on_browse(self, _):
        parent = None
        widget = self.icon_entry
        while widget:
            if isinstance(widget, Gtk.Window):
                parent = widget
                break
            widget = widget.get_parent()

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
