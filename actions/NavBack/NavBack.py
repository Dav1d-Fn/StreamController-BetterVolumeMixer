from src.backend.PluginManager.ActionBase import ActionBase
from loguru import logger as log
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio
import globals as gl
import os

ROW_OPTIONS = ["Custom Text"]
ROW_KEYS    = ["custom"]

DEFAULTS = {
    "custom_icon_path": "",
    "top_content":    "custom",
    "center_content": "custom",
    "bottom_content": "custom",
    "custom_top":    "",
    "custom_center": "Back",
    "custom_bottom": "",
}


class NavBack(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_ready(self):
        self.plugin_base.register_action(self)
        self._last_icon_path = None  # reset on each page load so icon is always redrawn
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
        try:
            serial = self.deck_controller.serial_number()
        except Exception:
            return
        origin = self.plugin_base.get_origin_page(serial)
        if origin:
            self._load_page(origin)

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
        self._update_labels()

    def _update_labels(self):
        self.set_top_label(self._resolve_label("top_content", "custom_top"))
        self.set_center_label(self._resolve_label("center_content", "custom_center"))
        self.set_bottom_label(self._resolve_label("bottom_content", "custom_bottom"))

    def _resolve_label(self, content_key, custom_key) -> str:
        s = self.get_settings()
        mode = s.get(content_key, DEFAULTS[content_key])
        return s.get(custom_key, DEFAULTS.get(custom_key, ""))

    def _update_display(self):
        s = self.get_settings()
        custom_icon = s.get("custom_icon_path", "").strip()
        if custom_icon and os.path.exists(custom_icon):
            icon_path = custom_icon
        else:
            default = os.path.join(self.plugin_base.PATH, "assets", "nav_back.png")
            icon_path = default if os.path.exists(default) else None
        if icon_path != self._last_icon_path:
            self._last_icon_path = icon_path
            self.set_media(media_path=icon_path, size=0.75)
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
