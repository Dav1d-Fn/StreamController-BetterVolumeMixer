from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.DeckManagement.InputIdentifier import Input
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, Gio, GLib
from PIL import Image, ImageDraw, ImageFont
import os
import tempfile


def _get_plugin_classes():
    from plugins.com_dav1dfn_BetterVolumeMixer.main import (
        BetterVolumeMixer, _PinnedPlaceholder, _MasterSink, MASTER_SINK_KEY
    )
    return BetterVolumeMixer, _PinnedPlaceholder, _MasterSink, MASTER_SINK_KEY


DEFAULTS = {
    "icon_scale": 0.55,
}

_FONT_PATHS = [
    "/usr/share/fonts/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/noto/NotoSans-Regular.ttf",
]


def _get_font(size: int) -> ImageFont.ImageFont:
    for path in _FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


class TouchscreenMixer(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._temp_path: str | None = None
        self._selected_app: str | None = None
        self._last_state_hash: str = ""

    def on_ready(self):
        self.plugin_base.register_action(self)
        s = self.get_settings()
        changed = False
        for k, v in DEFAULTS.items():
            if k not in s:
                s[k] = v
                changed = True
        if changed:
            self.set_settings(s)
        GLib.idle_add(self._update_display)

    def on_removed(self):
        self.plugin_base.unregister_action(self)
        self._clear_display()

    def event_callback(self, event, data=None):
        if event == Input.Touchscreen.Events.DRAG_LEFT:
            self.plugin_base.nav_right()
            self.plugin_base._notify_actions()
        elif event == Input.Touchscreen.Events.DRAG_RIGHT:
            self.plugin_base.nav_left()
            self.plugin_base._notify_actions()

    def on_sinks_updated(self):
        self._update_display()

    # ── On-demand display ─────────────────────────────────────────────────

    def _clear_display(self):
        try:
            page = self.deck_controller.active_page
            if page is not None:
                bg = (page.dict
                      .get("touchscreens", {})
                      .get("sd-plus", {})
                      .get("states", {})
                      .get("0", {})
                      .get("background", {}))
                bg.pop("image", None)
        except Exception:
            pass
        try:
            self.get_input().update()
        except Exception:
            pass

    # ── Rendering ─────────────────────────────────────────────────────────

    def _state_hash(self) -> str:
        _, _PinnedPlaceholder, _MasterSink, _ = _get_plugin_classes()
        s = self.get_settings()
        parts = [str(self.plugin_base.page_offset), str(s.get("icon_scale", DEFAULTS["icon_scale"]))]
        for i in range(4):
            idx = self.plugin_base.page_offset * 4 + i
            sinks = self.plugin_base.active_sinks
            sink = sinks[idx] if idx < len(sinks) else None
            if sink is None:
                parts.append("_")
            else:
                rk = self.plugin_base._app_raw_key(sink)
                vol = self.plugin_base._volume_cache.get(rk, 0)
                muted = (not isinstance(sink, (_PinnedPlaceholder, _MasterSink))) and sink.mute
                parts.append(f"{rk}:{vol}:{muted}")
        return "|".join(parts)

    def _update_display(self):
        try:
            h = self._state_hash()
            if h == self._last_state_hash:
                return
            self._last_state_hash = h
            img = self._render_image()
            if img is None:
                return

            # Write to a per-deck temp file
            serial = self.deck_controller.serial_number()
            temp_path = os.path.join(tempfile.gettempdir(), f"bvm_ts_{serial}.png")
            img.save(temp_path)
            self._temp_path = temp_path

            # Inject into the page's in-memory dict (no save() — keeps page JSON clean)
            page = self.deck_controller.active_page
            if page is None:
                return
            ts = page.dict.setdefault("touchscreens", {})
            slot = ts.setdefault("sd-plus", {})
            states = slot.setdefault("states", {})
            state0 = states.setdefault("0", {})
            state0.setdefault("background", {})["image"] = temp_path

            # Trigger touchscreen re-composite
            self.get_input().update()
        except Exception:
            pass

    def _render_image(self) -> Image.Image | None:
        try:
            _, _PinnedPlaceholder, _MasterSink, _ = _get_plugin_classes()
            s = self.get_settings()
            icon_scale = s.get("icon_scale", DEFAULTS["icon_scale"])

            w, h = 800, 100
            n_slots = 4
            slot_w = w // n_slots

            img = Image.new("RGBA", (w, h), (18, 18, 18, 255))
            draw = ImageDraw.Draw(img)

            font_name = _get_font(11)
            font_vol = _get_font(10)

            for i in range(n_slots):
                global_slot = self.plugin_base.page_offset * n_slots + i
                sinks = self.plugin_base.active_sinks
                sink = sinks[global_slot] if global_slot < len(sinks) else None

                x = i * slot_w

                # Divider
                if i > 0:
                    draw.line([(x, 8), (x, h - 8)], fill=(50, 50, 50, 255), width=1)

                if sink is None:
                    draw.text((x + slot_w // 2, h // 2), "—", fill=(80, 80, 80, 255),
                              font=font_name, anchor="mm")
                    continue

                raw_key = self.plugin_base._app_raw_key(sink)
                app_name = self.plugin_base._app_name(sink)
                vol = self.plugin_base._volume_cache.get(raw_key)
                is_placeholder = isinstance(sink, _PinnedPlaceholder)
                is_muted = (not is_placeholder) and (not isinstance(sink, _MasterSink)) and sink.mute

                # Icon
                icon_h = int(h * icon_scale)
                icon_w = icon_h
                icon_path = self._resolve_icon(sink, raw_key, app_name, is_placeholder)
                if icon_path:
                    try:
                        with Image.open(icon_path) as raw_img:
                            raw_img.seek(0)
                            icon = raw_img.convert("RGBA").resize((icon_w, icon_h), Image.LANCZOS)
                        ix = x + (slot_w - icon_w) // 2
                        iy = 4
                        img.paste(icon, (ix, iy), icon)
                    except Exception:
                        pass

                # App name
                cx = x + slot_w // 2
                draw.text((cx, h - 18), app_name[:10], fill=(220, 220, 220, 255),
                          font=font_name, anchor="ms")

                # Volume / mute
                if is_muted:
                    draw.text((cx, h - 6), "[M]", fill=(255, 80, 80, 255),
                              font=font_vol, anchor="ms")
                elif vol is not None:
                    draw.text((cx, h - 6), f"{vol}%", fill=(150, 150, 150, 255),
                              font=font_vol, anchor="ms")

            return img
        except Exception:
            return None

    def _resolve_icon(self, sink, raw_key, app_name, is_placeholder) -> str | None:
        _, _PinnedPlaceholder, _MasterSink, _ = _get_plugin_classes()
        custom_icons = self.plugin_base.get_custom_icons()
        if raw_key in custom_icons and os.path.exists(custom_icons[raw_key]):
            return custom_icons[raw_key]
        if is_placeholder or isinstance(sink, _MasterSink):
            return None
        icon_name = self.plugin_base._app_icon_name(sink)
        return self._find_icon(icon_name, app_name)

    def _find_icon(self, icon_name: str, app_name: str) -> str | None:
        if icon_name:
            p = self._gtk_icon_lookup(icon_name) or self._manual_icon_search(icon_name)
            if p:
                return p
        guessed = app_name.lower().replace(" ", "-")
        return self._gtk_icon_lookup(guessed) or self._manual_icon_search(guessed)

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
                f = info.get_file()
                if f:
                    p = f.get_path()
                    if p and os.path.exists(p):
                        return p
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

    # ── Settings UI ───────────────────────────────────────────────────────

    def get_config_rows(self) -> list:
        rows = []

        self.scale_spinner = Adw.SpinRow.new_with_range(0.1, 0.9, 0.05)
        self.scale_spinner.set_title("Icon Scale")
        self.scale_spinner.set_subtitle("Icon size relative to touchscreen height")
        rows.append(self.scale_spinner)

        rows.append(self._section("App Priority Order"))
        rows.append(self._hint("Apps shown in the mixer. Select a row to reorder, pin, rename, hide or set a custom icon."))

        self.priority_box = Gtk.ListBox()
        self.priority_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.priority_box.add_css_class("boxed-list")
        self.priority_box.connect("row-selected", self._on_row_selected)
        rows.append(self.priority_box)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        btn_row.set_margin_top(4)
        self.btn_up     = Gtk.Button(label="▲ Up")
        self.btn_down   = Gtk.Button(label="▼ Down")
        self.btn_pin    = Gtk.Button(label="📌 Pin")
        self.btn_rename = Gtk.Button(label="✏ Rename")
        self.btn_hide   = Gtk.Button(label="Hide")
        self.btn_delete = Gtk.Button(label="🗑 Delete")
        self.btn_hide.add_css_class("destructive-action")
        self.btn_delete.add_css_class("destructive-action")
        for b in (self.btn_up, self.btn_down, self.btn_pin, self.btn_rename, self.btn_hide, self.btn_delete):
            b.set_sensitive(False)
            btn_row.append(b)
        rows.append(btn_row)

        rows.append(self._section("Hidden Apps"))
        self.hidden_box = Gtk.ListBox()
        self.hidden_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.hidden_box.add_css_class("boxed-list")
        rows.append(self.hidden_box)

        self._load_config_values()

        self.scale_spinner.connect("changed", self._on_scale_changed)
        self.btn_up.connect("clicked", self._on_move_up)
        self.btn_down.connect("clicked", self._on_move_down)
        self.btn_pin.connect("clicked", self._on_toggle_pin)
        self.btn_rename.connect("clicked", self._on_rename)
        self.btn_hide.connect("clicked", self._on_hide)
        self.btn_delete.connect("clicked", self._on_delete)
        return rows

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
        self.scale_spinner.set_value(s.get("icon_scale", DEFAULTS["icon_scale"]))
        self._rebuild_priority_list()
        self._rebuild_hidden_list()

    def _on_scale_changed(self, *args):
        s = self.get_settings()
        s["icon_scale"] = round(self.scale_spinner.get_value(), 2)
        self.set_settings(s)
        self._update_display()

    # ── Priority / Hidden list (shared with AppDisplay) ───────────────────

    def _display_name_for_key(self, raw_key: str) -> str:
        BetterVolumeMixer, _PinnedPlaceholder, _MasterSink, MASTER_SINK_KEY = _get_plugin_classes()
        if raw_key == MASTER_SINK_KEY:
            return self.plugin_base.get_display_name_overrides().get(MASTER_SINK_KEY, "System")
        overrides = self.plugin_base.get_display_name_overrides()
        if raw_key in overrides:
            return overrides[raw_key]
        parts = raw_key.split("|", 1)
        binary = parts[1] if len(parts) == 2 and parts[1] else parts[0]
        return BetterVolumeMixer.KNOWN_BINARY_ALIASES.get(binary, binary)

    def _clear_box(self, box):
        child = box.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt

    def _rebuild_priority_list(self):
        self._clear_box(self.priority_box)
        self._selected_app = None
        for b in (self.btn_up, self.btn_down, self.btn_pin, self.btn_rename, self.btn_hide, self.btn_delete):
            b.set_sensitive(False)

        BetterVolumeMixer, _PinnedPlaceholder, _MasterSink, MASTER_SINK_KEY = _get_plugin_classes()
        priority = self.plugin_base.get_priority_list()
        hidden   = self.plugin_base.get_hidden_list()
        pinned   = self.plugin_base.get_pinned_list()
        custom_icons = self.plugin_base.get_custom_icons()

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

        for raw_key in visible:
            is_master = (raw_key == MASTER_SINK_KEY)
            is_pinned = raw_key in pinned
            display   = self._display_name_for_key(raw_key)

            row = Adw.ActionRow()
            title = ("📌 " if is_pinned else "") + display
            row.set_title(title)
            if is_master:
                row.set_subtitle("Master output volume")
            else:
                parts = raw_key.split("|", 1)
                subtitle_parts = []
                if parts[0] and parts[0] != display:
                    subtitle_parts.append(parts[0])
                if len(parts) == 2 and parts[1] and parts[1] != display:
                    subtitle_parts.append(parts[1])
                if subtitle_parts:
                    row.set_subtitle(" · ".join(subtitle_parts))

            if raw_key in custom_icons:
                extra = f"icon: {os.path.basename(custom_icons[raw_key])}"
                row.set_subtitle((row.get_subtitle() + " · " if row.get_subtitle() else "") + extra)

            icon_btn = Gtk.Button(label="🖼")
            icon_btn.set_valign(Gtk.Align.CENTER)
            icon_btn.add_css_class("flat")
            icon_btn.set_tooltip_text("Set custom icon")
            icon_btn.connect("clicked", lambda _, k=raw_key: self._on_set_icon(k))
            row.add_suffix(icon_btn)

            listrow = Gtk.ListBoxRow()
            listrow._app_name = raw_key
            listrow._is_master = is_master
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
        for raw_key in hidden:
            display = self._display_name_for_key(raw_key)
            row = Adw.ActionRow()
            row.set_title(display)
            btn = Gtk.Button(label="Show")
            btn.set_valign(Gtk.Align.CENTER)
            btn.add_css_class("flat")
            btn.connect("clicked", self._on_unhide, raw_key)
            row.add_suffix(btn)
            self.hidden_box.append(row)

    def _visible_priority(self) -> list[str]:
        hidden = self.plugin_base.get_hidden_list()
        return [p for p in self.plugin_base.get_priority_list() if p not in hidden]

    def _reselect(self, app: str):
        row = self.priority_box.get_first_child()
        while row:
            if isinstance(row, Gtk.ListBoxRow) and getattr(row, "_app_name", None) == app:
                self.priority_box.select_row(row)
                self._selected_app = app
                for b in (self.btn_up, self.btn_down, self.btn_pin, self.btn_rename, self.btn_hide, self.btn_delete):
                    b.set_sensitive(True)
                pinned = self.plugin_base.get_pinned_list()
                self.btn_pin.set_label("📌 Unpin" if app in pinned else "📌 Pin")
                return
            row = row.get_next_sibling()

    def _on_row_selected(self, listbox, row):
        if row is None or not hasattr(row, "_app_name"):
            self._selected_app = None
            for b in (self.btn_up, self.btn_down, self.btn_pin, self.btn_rename, self.btn_hide, self.btn_delete):
                b.set_sensitive(False)
        else:
            self._selected_app = row._app_name
            is_master = getattr(row, "_is_master", False)
            for b in (self.btn_up, self.btn_down, self.btn_pin, self.btn_rename, self.btn_hide, self.btn_delete):
                b.set_sensitive(True)
            self.btn_hide.set_sensitive(not is_master)
            self.btn_delete.set_sensitive(not is_master)
            pinned = self.plugin_base.get_pinned_list()
            self.btn_pin.set_label("📌 Unpin" if self._selected_app in pinned else "📌 Pin")

    def _save_reordered(self, visible: list[str]):
        hidden = self.plugin_base.get_hidden_list()
        hidden_entries = [p for p in self.plugin_base.get_priority_list() if p in hidden]
        self.plugin_base.set_priority_list(visible + hidden_entries)

    def _on_move_up(self, _):
        if not self._selected_app:
            return
        visible = self._visible_priority()
        idx = visible.index(self._selected_app) if self._selected_app in visible else -1
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
        idx = visible.index(self._selected_app) if self._selected_app in visible else -1
        if idx < 0 or idx >= len(visible) - 1:
            return
        visible[idx], visible[idx + 1] = visible[idx + 1], visible[idx]
        self._save_reordered(visible)
        self._rebuild_priority_list()
        self._reselect(self._selected_app)
        self.plugin_base._refresh_sinks()

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

    def _on_unhide(self, _, raw_key: str):
        hidden = self.plugin_base.get_hidden_list()
        if raw_key in hidden:
            hidden.remove(raw_key)
            self.plugin_base.set_hidden_list(hidden)
        self._rebuild_priority_list()
        self._rebuild_hidden_list()
        self.plugin_base._refresh_sinks()

    def _on_delete(self, _):
        if not self._selected_app:
            return
        _, _PP, _MS, MASTER_SINK_KEY = _get_plugin_classes()
        if self._selected_app == MASTER_SINK_KEY:
            return
        key = self._selected_app
        priority = [p for p in self.plugin_base.get_priority_list() if p != key]
        hidden   = [p for p in self.plugin_base.get_hidden_list()   if p != key]
        pinned   = [p for p in self.plugin_base.get_pinned_list()   if p != key]
        overrides = self.plugin_base.get_display_name_overrides()
        overrides.pop(key, None)
        icons = self.plugin_base.get_custom_icons()
        icons.pop(key, None)
        self.plugin_base.set_priority_list(priority)
        self.plugin_base.set_hidden_list(hidden)
        self.plugin_base.set_pinned_list(pinned)
        self.plugin_base.set_display_name_overrides(overrides)
        self.plugin_base.set_custom_icons(icons)
        self._selected_app = None
        self._rebuild_priority_list()
        self._rebuild_hidden_list()
        self.plugin_base._refresh_sinks()

    def _on_toggle_pin(self, _):
        if not self._selected_app:
            return
        pinned = self.plugin_base.get_pinned_list()
        if self._selected_app in pinned:
            pinned.remove(self._selected_app)
            self.btn_pin.set_label("📌 Pin")
        else:
            pinned.append(self._selected_app)
            self.btn_pin.set_label("📌 Unpin")
        self.plugin_base.set_pinned_list(pinned)
        self._rebuild_priority_list()
        self._reselect(self._selected_app)
        self.plugin_base._refresh_sinks()

    def _on_rename(self, _):
        if not self._selected_app:
            return
        raw_key = self._selected_app
        current = self._display_name_for_key(raw_key)

        parent = self._get_parent_window()
        dialog = Adw.MessageDialog(
            transient_for=parent, modal=True,
            heading="Rename",
            body=f'Set a custom display name for "{current}".',
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("Display name…")
        entry.set_text(current)
        entry.set_margin_top(8)
        entry.set_margin_bottom(4)
        entry.set_margin_start(4)
        entry.set_margin_end(4)
        dialog.set_extra_child(entry)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("reset", "Reset to default")
        dialog.set_response_appearance("reset", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.add_response("set", "Rename")
        dialog.set_response_appearance("set", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("set")
        dialog.set_close_response("cancel")

        def on_response(d, response):
            o = self.plugin_base.get_display_name_overrides()
            if response == "set":
                name = entry.get_text().strip()
                if name:
                    o[raw_key] = name
                    self.plugin_base.set_display_name_overrides(o)
            elif response == "reset":
                o.pop(raw_key, None)
                self.plugin_base.set_display_name_overrides(o)
            self._rebuild_priority_list()
            self._reselect(raw_key)
            self.plugin_base._notify_actions()
            d.destroy()

        dialog.connect("response", on_response)
        entry.connect("activate", lambda _: dialog.response("set"))
        dialog.present()

    def _on_set_icon(self, raw_key: str):
        custom_icons = self.plugin_base.get_custom_icons()
        parent = self._get_parent_window()
        display = self._display_name_for_key(raw_key)
        dialog = Adw.MessageDialog(
            transient_for=parent, modal=True,
            heading=f"Custom icon for {display}",
            body="Enter the absolute path to a PNG, SVG or GIF file.",
        )
        entry = Gtk.Entry()
        entry.set_placeholder_text("/home/user/icons/app.png")
        entry.set_margin_top(8)
        entry.set_margin_bottom(4)
        entry.set_margin_start(4)
        entry.set_margin_end(4)
        if raw_key in custom_icons:
            entry.set_text(custom_icons[raw_key])

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
            filters = Gio.ListStore.new(Gtk.FileFilter)
            filters.append(f)
            fd.set_filters(filters)
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
        if raw_key in custom_icons:
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
                    icons[raw_key] = path
                    self.plugin_base.set_custom_icons(icons)
                    self._rebuild_priority_list()
                    self.plugin_base._notify_actions()
                    self._update_display()
            elif response == "clear":
                icons.pop(raw_key, None)
                self.plugin_base.set_custom_icons(icons)
                self._rebuild_priority_list()
                self.plugin_base._notify_actions()
                self._update_display()
            d.destroy()

        dialog.connect("response", on_response)
        entry.connect("activate", lambda _: dialog.response("set"))
        dialog.present()

    def _get_parent_window(self):
        try:
            widget = self.scale_spinner
            while widget:
                if isinstance(widget, Gtk.Window):
                    return widget
                widget = widget.get_parent()
        except Exception:
            pass
        return None
