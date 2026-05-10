from src.backend.PluginManager.ActionBase import ActionBase
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GdkPixbuf, Gio
import os


ROW_OPTIONS = ["Empty", "App Name", "Volume %", "Custom Text"]
ROW_KEYS    = ["empty", "appname", "volume", "custom"]

DEFAULTS = {
    "slot_index":     0,
    "show_icon":      True,
    "top_content":    "appname",
    "center_content": "custom",
    "bottom_content": "volume",
    "custom_top":     "",
    "custom_center":  "",
    "custom_bottom":  "",
    "sync_settings":  True,
}


class AppDisplay(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._selected_app: str | None = None
        self._config_open = False

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
        slot = self.get_settings().get("slot_index", 0)
        self.plugin_base.toggle_mute(slot)

    def on_sinks_updated(self):
        self._update_display()

    def _resolve_label(self, content_key, custom_key, slot, sink) -> str:
        s = self.get_settings()
        mode = s.get(content_key, DEFAULTS[content_key])
        if mode == "appname":
            return self.plugin_base._app_name(sink)[:10] if sink else ""
        elif mode == "volume":
            if sink is None:
                return ""
            vol = self.plugin_base.get_volume(slot)
            prefix = "[M] " if sink.mute else ""
            return f"{prefix}{vol}%" if vol is not None else ""
        return s.get(custom_key, "")

    def _update_display(self):
        s = self.get_settings()
        slot = s.get("slot_index", 0)
        show_icon = s.get("show_icon", True)
        sink = self.plugin_base.get_sink_for_slot(slot)

        if sink is None:
            self.set_media(media_path=None)
            self.set_top_label("")
            self.set_center_label("—")
            self.set_bottom_label("")
            return

        app_name = self.plugin_base._app_name(sink)

        # Icon
        if show_icon:
            custom_icons = self.plugin_base.get_custom_icons()
            if app_name in custom_icons and os.path.exists(custom_icons[app_name]):
                icon_path = custom_icons[app_name]
            else:
                icon_path = self._find_icon(self.plugin_base._app_icon_name(sink), app_name)
            self.set_media(media_path=icon_path, size=0.6) if icon_path else self.set_media(media_path=None)
        else:
            self.set_media(media_path=None)

        self.set_top_label(self._resolve_label("top_content", "custom_top", slot, sink))
        self.set_center_label(self._resolve_label("center_content", "custom_center", slot, sink))
        self.set_bottom_label(self._resolve_label("bottom_content", "custom_bottom", slot, sink))

    def _find_icon(self, icon_name: str, app_name: str) -> str | None:
        if icon_name:
            path = self._gtk_icon_lookup(icon_name)
            if path:
                return path
        if icon_name:
            path = self._manual_icon_search(icon_name)
            if path:
                return path
        guessed = app_name.lower().replace(" ", "-")
        path = self._gtk_icon_lookup(guessed)
        if path:
            return path
        return self._manual_icon_search(guessed)

    def _gtk_icon_lookup(self, name: str) -> str | None:
        try:
            theme = Gtk.IconTheme.get_for_display(Gtk.Widget.get_display(Gtk.Button()))
        except Exception:
            try:
                theme = Gtk.IconTheme.new()
                theme.set_theme_name("hicolor")
            except Exception:
                return None
        try:
            info = theme.lookup_icon(name, [], 64, 1, Gtk.TextDirection.NONE, 0)
            if info:
                file_obj = info.get_file()
                if file_obj:
                    path = file_obj.get_path()
                    if path and os.path.exists(path):
                        return path
        except Exception:
            pass
        return None

    def _manual_icon_search(self, name: str) -> str | None:
        dirs = [
            "/usr/share/icons/hicolor/64x64/apps",
            "/usr/share/icons/hicolor/48x48/apps",
            "/usr/share/icons/hicolor/128x128/apps",
            "/usr/share/icons/Adwaita/48x48/apps",
            os.path.expanduser("~/.local/share/icons/hicolor/64x64/apps"),
            os.path.expanduser("~/.local/share/icons/hicolor/48x48/apps"),
            "/usr/share/pixmaps",
            os.path.expanduser("~/.local/share/flatpak/exports/share/icons/hicolor/64x64/apps"),
            "/var/lib/flatpak/exports/share/icons/hicolor/64x64/apps",
        ]
        for d in dirs:
            for ext in ("png", "svg", "xpm"):
                p = os.path.join(d, f"{name}.{ext}")
                if os.path.exists(p):
                    return p
        return None

    # ── Settings UI ────────────────────────────────────────────────────────

    def get_config_rows(self) -> list:
        self._config_open = True
        rows = []

        self.slot_spinner = Adw.SpinRow.new_with_range(0, 3, 1)
        self.slot_spinner.set_title("Column Slot (0–3)")
        rows.append(self.slot_spinner)

        self.sync_row = Adw.SwitchRow()
        self.sync_row.set_title("Sync settings to all App Display buttons")
        self.sync_row.set_subtitle("Changes here apply to all App Display actions")
        rows.append(self.sync_row)

        self.show_icon_row = Adw.SwitchRow()
        self.show_icon_row.set_title("Show App Icon")
        rows.append(self.show_icon_row)

        self.top_combo, self.top_entry = self._make_label_row("Top Label", rows)
        self.center_combo, self.center_entry = self._make_label_row("Center Label", rows)
        self.bottom_combo, self.bottom_entry = self._make_label_row("Bottom Label", rows)

        rows.append(self._section("App Priority Order"))
        rows.append(self._hint("Apps shown first in the mixer. Click a row to select, then move or hide it."))

        self.priority_box = Gtk.ListBox()
        self.priority_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.priority_box.add_css_class("boxed-list")
        self.priority_box.connect("row-selected", self._on_row_selected)
        rows.append(self.priority_box)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_row.set_margin_top(4)
        self.btn_up   = Gtk.Button(label="▲ Up")
        self.btn_down = Gtk.Button(label="▼ Down")
        self.btn_hide = Gtk.Button(label="Hide")
        self.btn_hide.add_css_class("destructive-action")
        for b in (self.btn_up, self.btn_down, self.btn_hide):
            b.set_sensitive(False)
            btn_row.append(b)
        rows.append(btn_row)

        rows.append(self._section("Hidden Apps"))
        self.hidden_box = Gtk.ListBox()
        self.hidden_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.hidden_box.add_css_class("boxed-list")
        rows.append(self.hidden_box)

        self._load_config_values()

        self.slot_spinner.connect("changed", self._on_display_changed)
        self.sync_row.connect("notify::active", self._on_display_changed)
        self.show_icon_row.connect("notify::active", self._on_display_changed)
        for combo, entry in [(self.top_combo, self.top_entry),
                             (self.center_combo, self.center_entry),
                             (self.bottom_combo, self.bottom_entry)]:
            combo.connect("notify::selected", lambda w, _, e=entry: (
                e.set_sensitive(ROW_KEYS[w.get_selected()] == "custom"),
                self._on_display_changed()
            ))
            entry.connect("changed", self._on_display_changed)
        self.btn_up.connect("clicked", self._on_move_up)
        self.btn_down.connect("clicked", self._on_move_down)
        self.btn_hide.connect("clicked", self._on_hide)
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

    def _section(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=f"<b>{text}</b>")
        lbl.set_use_markup(True)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_margin_top(14)
        lbl.set_margin_start(6)
        return lbl

    def _hint(self, text: str) -> Gtk.Label:
        lbl = Gtk.Label(label=text)
        lbl.set_halign(Gtk.Align.START)
        lbl.set_wrap(True)
        lbl.set_margin_start(6)
        return lbl

    def _load_config_values(self):
        s = self.get_settings()
        self.slot_spinner.set_value(s.get("slot_index", DEFAULTS["slot_index"]))
        self.sync_row.set_active(s.get("sync_settings", DEFAULTS["sync_settings"]))
        self.show_icon_row.set_active(s.get("show_icon", DEFAULTS["show_icon"]))

        def load_combo(combo, entry, ck, cust):
            mode = s.get(ck, DEFAULTS[ck])
            combo.set_selected(ROW_KEYS.index(mode) if mode in ROW_KEYS else 0)
            entry.set_text(s.get(cust, ""))
            entry.set_sensitive(mode == "custom")

        load_combo(self.top_combo,    self.top_entry,    "top_content",    "custom_top")
        load_combo(self.center_combo, self.center_entry, "center_content", "custom_center")
        load_combo(self.bottom_combo, self.bottom_entry, "bottom_content", "custom_bottom")
        self._rebuild_priority_list()
        self._rebuild_hidden_list()

    def _on_display_changed(self, *args):
        s = self.get_settings()
        s["slot_index"]      = int(self.slot_spinner.get_value())
        s["sync_settings"]   = self.sync_row.get_active()
        s["show_icon"]       = self.show_icon_row.get_active()
        s["top_content"]     = ROW_KEYS[self.top_combo.get_selected()]
        s["center_content"]  = ROW_KEYS[self.center_combo.get_selected()]
        s["bottom_content"]  = ROW_KEYS[self.bottom_combo.get_selected()]
        s["custom_top"]      = self.top_entry.get_text()
        s["custom_center"]   = self.center_entry.get_text()
        s["custom_bottom"]   = self.bottom_entry.get_text()
        self.set_settings(s)
        if s["sync_settings"]:
            self._sync_to_siblings(s)
        self._update_display()

    def _sync_to_siblings(self, settings: dict):
        sync_keys = ["sync_settings", "show_icon", "top_content", "center_content",
                     "bottom_content", "custom_top", "custom_center", "custom_bottom"]
        for action in self.plugin_base._registered_actions:
            if action is self or type(action).__name__ != "AppDisplay":
                continue
            try:
                s = action.get_settings()
                for k in sync_keys:
                    s[k] = settings[k]
                action.set_settings(s)
                action._update_display()
            except Exception:
                pass

    # ── Priority / Hidden list ─────────────────────────────────────────────

    def _clear_box(self, box):
        child = box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    def _rebuild_priority_list(self):
        self._clear_box(self.priority_box)
        self._selected_app = None
        for b in (self.btn_up, self.btn_down, self.btn_hide):
            b.set_sensitive(False)

        priority = self.plugin_base.get_priority_list()
        hidden   = self.plugin_base.get_hidden_list()

        visible = [p for p in priority if p not in hidden]
        if not visible:
            row = Gtk.ListBoxRow()
            row.set_activatable(False)
            lbl = Gtk.Label(label="No apps detected yet")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_margin_start(12)
            lbl.set_margin_top(8)
            lbl.set_margin_bottom(8)
            row.set_child(lbl)
            self.priority_box.append(row)
            return

        custom_icons = self.plugin_base.get_custom_icons()
        for app in visible:
            row = Adw.ActionRow()
            row.set_title(app)
            row._app_name = app
            if app in custom_icons:
                row.set_subtitle(os.path.basename(custom_icons[app]))

            icon_btn = Gtk.Button(label="🖼")
            icon_btn.set_valign(Gtk.Align.CENTER)
            icon_btn.add_css_class("flat")
            icon_btn.set_tooltip_text("Set custom icon")
            icon_btn.connect("clicked", lambda _, a=app, r=row: self._on_set_icon(a, r))
            row.add_suffix(icon_btn)

            listrow = Gtk.ListBoxRow()
            listrow._app_name = app
            listrow.set_child(row)
            self.priority_box.append(listrow)

    def _rebuild_hidden_list(self):
        self._clear_box(self.hidden_box)
        hidden = self.plugin_base.get_hidden_list()

        if not hidden:
            row = Gtk.ListBoxRow()
            row.set_activatable(False)
            lbl = Gtk.Label(label="No hidden apps")
            lbl.set_halign(Gtk.Align.START)
            lbl.set_margin_start(12)
            lbl.set_margin_top(8)
            lbl.set_margin_bottom(8)
            row.set_child(lbl)
            self.hidden_box.append(row)
            return

        for app in hidden:
            row = Adw.ActionRow()
            row.set_title(app)
            btn = Gtk.Button(label="Show")
            btn.set_valign(Gtk.Align.CENTER)
            btn.add_css_class("flat")
            btn.connect("clicked", self._on_unhide, app)
            row.add_suffix(btn)
            self.hidden_box.append(row)

    def _reselect(self, app: str):
        row = self.priority_box.get_first_child()
        while row:
            if isinstance(row, Gtk.ListBoxRow) and getattr(row, "_app_name", None) == app:
                self.priority_box.select_row(row)
                self._selected_app = app
                for b in (self.btn_up, self.btn_down, self.btn_hide):
                    b.set_sensitive(True)
                return
            row = row.get_next_sibling()

    def _visible_priority(self) -> list[str]:
        hidden = self.plugin_base.get_hidden_list()
        return [p for p in self.plugin_base.get_priority_list() if p not in hidden]

    def _on_row_selected(self, listbox, row):
        if row is None or not hasattr(row, "_app_name"):
            self._selected_app = None
            for b in (self.btn_up, self.btn_down, self.btn_hide):
                b.set_sensitive(False)
        else:
            self._selected_app = row._app_name
            for b in (self.btn_up, self.btn_down, self.btn_hide):
                b.set_sensitive(True)

    def _on_move_up(self, _):
        if not self._selected_app:
            return
        visible = self._visible_priority()
        if self._selected_app not in visible:
            return
        idx = visible.index(self._selected_app)
        if idx <= 0:
            return
        visible[idx], visible[idx - 1] = visible[idx - 1], visible[idx]
        self._save_reordered(visible)
        self._rebuild_priority_list()
        self._reselect(self._selected_app)
        self.plugin_base._refresh_sinks()

    def _on_move_down(self, _):
        if not self._selected_app:
            return
        visible = self._visible_priority()
        if self._selected_app not in visible:
            return
        idx = visible.index(self._selected_app)
        if idx >= len(visible) - 1:
            return
        visible[idx], visible[idx + 1] = visible[idx + 1], visible[idx]
        self._save_reordered(visible)
        self._rebuild_priority_list()
        self._reselect(self._selected_app)
        self.plugin_base._refresh_sinks()

    def _save_reordered(self, visible: list[str]):
        hidden = self.plugin_base.get_hidden_list()
        hidden_entries = [p for p in self.plugin_base.get_priority_list() if p in hidden]
        self.plugin_base.set_priority_list(visible + hidden_entries)

    def _on_hide(self, _):
        if not self._selected_app:
            return
        hidden = self.plugin_base.get_hidden_list()
        if self._selected_app not in hidden:
            hidden.append(self._selected_app)
            self.plugin_base.set_hidden_list(hidden)
        self._selected_app = None
        self._rebuild_priority_list()
        self._rebuild_hidden_list()
        self.plugin_base._refresh_sinks()

    def _on_unhide(self, _, app: str):
        hidden = self.plugin_base.get_hidden_list()
        if app in hidden:
            hidden.remove(app)
            self.plugin_base.set_hidden_list(hidden)
        self._rebuild_priority_list()
        self._rebuild_hidden_list()
        self.plugin_base._refresh_sinks()

    def _on_set_icon(self, app: str, action_row):
        custom_icons = self.plugin_base.get_custom_icons()

        parent = None
        widget = self.priority_box
        while widget:
            if isinstance(widget, Gtk.Window):
                parent = widget
                break
            widget = widget.get_parent()

        dialog = Adw.MessageDialog(
            transient_for=parent,
            modal=True,
            heading=f"Custom icon for {app}",
            body="Enter the absolute path to a PNG or SVG file.",
        )

        entry = Gtk.Entry()
        entry.set_placeholder_text("/home/user/icons/spotify.png")
        entry.set_margin_top(8)
        entry.set_margin_bottom(4)
        entry.set_margin_start(4)
        entry.set_margin_end(4)
        if app in custom_icons:
            entry.set_text(custom_icons[app])

        browse_btn = Gtk.Button(label="Browse…")
        browse_btn.set_margin_start(4)
        browse_btn.set_margin_end(4)
        browse_btn.set_margin_bottom(4)

        def on_browse(_):
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
                        entry.set_text(file.get_path())
                except Exception:
                    pass
            fd.open(parent, None, on_done)

        browse_btn.connect("clicked", on_browse)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.append(entry)
        box.append(browse_btn)
        dialog.set_extra_child(box)

        dialog.add_response("cancel", "Cancel")
        if app in custom_icons:
            dialog.add_response("clear", "Clear Icon")
            dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("set", "Set Icon")
        dialog.set_response_appearance("set", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("set")
        dialog.set_close_response("cancel")

        def on_response(d, response):
            icons = self.plugin_base.get_custom_icons()
            if response == "set":
                path = entry.get_text().strip()
                if path and os.path.exists(path):
                    icons[app] = path
                    self.plugin_base.set_custom_icons(icons)
                    self._rebuild_priority_list()
                    self.plugin_base._notify_actions()
            elif response == "clear":
                icons.pop(app, None)
                self.plugin_base.set_custom_icons(icons)
                self._rebuild_priority_list()
                self.plugin_base._notify_actions()
            d.destroy()

        dialog.connect("response", on_response)
        entry.connect("activate", lambda _: dialog.response("set"))
        dialog.present()
