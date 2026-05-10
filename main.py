from src.backend.PluginManager.PluginBase import PluginBase
from src.backend.PluginManager.ActionHolder import ActionHolder
from src.backend.DeckManagement.InputIdentifier import Input
from src.backend.PluginManager.ActionInputSupport import ActionInputSupport

import sys, os, threading, time, json

import pulsectl

sys.path.append(os.path.dirname(__file__))

from plugins.com_dav1dfn_BetterVolumeMixer.actions.OpenMixer.OpenMixer import OpenMixer
from plugins.com_dav1dfn_BetterVolumeMixer.actions.NavBack.NavBack import NavBack
from plugins.com_dav1dfn_BetterVolumeMixer.actions.NavRight.NavRight import NavRight
from plugins.com_dav1dfn_BetterVolumeMixer.actions.NavLeft.NavLeft import NavLeft
from plugins.com_dav1dfn_BetterVolumeMixer.actions.VolumeUp.VolumeUp import VolumeUp
from plugins.com_dav1dfn_BetterVolumeMixer.actions.VolumeDown.VolumeDown import VolumeDown
from plugins.com_dav1dfn_BetterVolumeMixer.actions.AppDisplay.AppDisplay import AppDisplay

SLOTS_PER_PAGE = 4


class BetterVolumeMixer(PluginBase):
    def __init__(self):
        super().__init__()

        self.pulse = pulsectl.Pulse("volume-mixer-pro", threading_lock=True)
        self.active_sinks: list = []
        self.page_offset: int = 0
        self._registered_actions: list = []
        self._plugin_settings: dict = self._load_plugin_settings()

        self._stop_polling = threading.Event()
        self._poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._poll_thread.start()

        key_only = {
            Input.Key: ActionInputSupport.SUPPORTED,
            Input.Dial: ActionInputSupport.UNSUPPORTED,
            Input.Touchscreen: ActionInputSupport.UNSUPPORTED,
        }

        self.add_action_holder(ActionHolder(plugin_base=self, action_base=OpenMixer,
            action_id_suffix="OpenMixer", action_name="Open Mixer", action_support=key_only))
        self.add_action_holder(ActionHolder(plugin_base=self, action_base=NavBack,
            action_id_suffix="NavBack", action_name="Nav: Back to Main", action_support=key_only))
        self.add_action_holder(ActionHolder(plugin_base=self, action_base=NavRight,
            action_id_suffix="NavRight", action_name="Nav: Next Page →", action_support=key_only))
        self.add_action_holder(ActionHolder(plugin_base=self, action_base=NavLeft,
            action_id_suffix="NavLeft", action_name="Nav: Previous Page ←", action_support=key_only))
        self.add_action_holder(ActionHolder(plugin_base=self, action_base=VolumeUp,
            action_id_suffix="VolumeUp", action_name="Volume Up", action_support=key_only))
        self.add_action_holder(ActionHolder(plugin_base=self, action_base=VolumeDown,
            action_id_suffix="VolumeDown", action_name="Volume Down", action_support=key_only))
        self.add_action_holder(ActionHolder(plugin_base=self, action_base=AppDisplay,
            action_id_suffix="AppDisplay", action_name="App Display", action_support=key_only))

        self.register(
            plugin_name="Better Volume Mixer",
            github_repo="https://github.com/dav1d-fn/BetterVolumeMixer",
            plugin_version="1.0.0",
            app_version="1.0.0-alpha",
        )

        self.register_page(os.path.join(self.PATH, "pages", "BetterVolumeMixer.json"))

    # ── Page paths ────────────────────────────────────────────────────────

    def mixer_page_path(self) -> str:
        return os.path.join(self.PATH, "pages", "BetterVolumeMixer.json")

    def main_page_path(self) -> str:
        pages_dir = os.path.join(
            os.path.expanduser("~"),
            ".var", "app", "com.core447.StreamController", "data", "pages"
        )
        for name in ("Main.json", "main.json"):
            p = os.path.join(pages_dir, name)
            if os.path.exists(p):
                return p
        try:
            for f in sorted(os.listdir(pages_dir)):
                if f.endswith(".json"):
                    return os.path.join(pages_dir, f)
        except Exception:
            pass
        return ""

    # ── Plugin settings ───────────────────────────────────────────────────

    def _settings_path(self) -> str:
        return os.path.join(self.PATH, "plugin_settings.json")

    def _load_plugin_settings(self) -> dict:
        path = self._settings_path()
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {"priority_list": [], "hidden_list": []}

    def save_plugin_settings(self):
        try:
            with open(self._settings_path(), "w") as f:
                json.dump(self._plugin_settings, f, indent=2)
        except Exception:
            pass

    def get_priority_list(self) -> list[str]:
        return self._plugin_settings.get("priority_list", [])

    def set_priority_list(self, lst: list[str]):
        self._plugin_settings["priority_list"] = lst
        self.save_plugin_settings()

    def get_hidden_list(self) -> list[str]:
        return self._plugin_settings.get("hidden_list", [])

    def set_hidden_list(self, lst: list[str]):
        self._plugin_settings["hidden_list"] = lst
        self.save_plugin_settings()

    def get_custom_icons(self) -> dict[str, str]:
        return self._plugin_settings.get("custom_icons", {})

    def set_custom_icons(self, d: dict[str, str]):
        self._plugin_settings["custom_icons"] = d
        self.save_plugin_settings()

    # ── PulseAudio polling ────────────────────────────────────────────────

    def _poll_loop(self):
        while not self._stop_polling.is_set():
            try:
                self._refresh_sinks()
            except Exception:
                pass
            time.sleep(1.0)

    def _refresh_sinks(self):
        try:
            # Always fetch fresh list — pulsectl only returns currently active sinks
            all_sinks = self.pulse.sink_input_list()
        except Exception:
            return

        hidden = self.get_hidden_list()
        priority = self.get_priority_list()

        # Auto-register newly seen apps into priority list
        known = set(priority + hidden)
        changed = False
        for s in all_sinks:
            name = self._app_name(s)
            if name and name not in known:
                priority.append(name)
                known.add(name)
                changed = True
        if changed:
            self.set_priority_list(priority)

        # Filter hidden, sort by priority
        visible = [s for s in all_sinks if self._app_name(s) not in hidden]

        def sort_key(sink):
            try:
                return priority.index(self._app_name(sink))
            except ValueError:
                return len(priority)

        self.active_sinks = sorted(visible, key=sort_key)

        max_offset = max(0, (len(self.active_sinks) - 1) // SLOTS_PER_PAGE)
        if self.page_offset > max_offset:
            self.page_offset = max_offset

        self._notify_actions()

    def _app_name(self, sink) -> str:
        p = sink.proplist
        return (p.get("application.name")
                or p.get("application.process.binary")
                or p.get("media.name")
                or "Unknown")

    def _app_icon_name(self, sink) -> str:
        return sink.proplist.get("application.icon_name", "")

    def _app_binary(self, sink) -> str:
        return sink.proplist.get("application.process.binary", "")

    # ── Icon resolution ───────────────────────────────────────────────────

    def resolve_icon(self, sink) -> str | None:
        """Find an icon for a sink — same logic that worked before."""
        icon_name = self._app_icon_name(sink)
        if not icon_name:
            return None

        search_dirs = [
            "/usr/share/icons/hicolor/64x64/apps",
            "/usr/share/icons/hicolor/48x48/apps",
            "/usr/share/icons/Adwaita/48x48/apps",
            os.path.expanduser("~/.local/share/icons/hicolor/48x48/apps"),
            "/usr/share/pixmaps",
        ]
        for d in search_dirs:
            for ext in ("png", "svg", "xpm"):
                p = os.path.join(d, f"{icon_name}.{ext}")
                if os.path.exists(p):
                    return p
        return None

    # ── Slot/volume helpers ───────────────────────────────────────────────

    def get_sink_for_slot(self, slot: int):
        idx = self.page_offset * SLOTS_PER_PAGE + slot
        if 0 <= idx < len(self.active_sinks):
            return self.active_sinks[idx]
        return None

    def get_volume(self, slot: int) -> int | None:
        sink = self.get_sink_for_slot(slot)
        if sink is None:
            return None
        try:
            return round(self.pulse.volume_get_all_chans(sink) * 100)
        except Exception:
            return None

    def change_volume(self, slot: int, delta: float):
        sink = self.get_sink_for_slot(slot)
        if sink is None:
            return
        try:
            vol = self.pulse.volume_get_all_chans(sink)
            self.pulse.volume_set_all_chans(sink, max(0.0, min(1.5, vol + delta)))
            self._notify_actions()
        except Exception:
            pass

    def toggle_mute(self, slot: int):
        sink = self.get_sink_for_slot(slot)
        if sink is None:
            return
        try:
            self.pulse.sink_input_mute(sink.index, not sink.mute)
            self._refresh_sinks()
        except Exception:
            pass

    # ── Navigation ────────────────────────────────────────────────────────

    def total_pages(self) -> int:
        return max(1, (len(self.active_sinks) + SLOTS_PER_PAGE - 1) // SLOTS_PER_PAGE)

    def nav_right(self):
        if self.page_offset < self.total_pages() - 1:
            self.page_offset += 1
            self._notify_actions()

    def nav_left(self):
        if self.page_offset > 0:
            self.page_offset -= 1
            self._notify_actions()

    # ── Action registry ───────────────────────────────────────────────────

    def register_action(self, action):
        if action not in self._registered_actions:
            self._registered_actions.append(action)

    def unregister_action(self, action):
        if action in self._registered_actions:
            self._registered_actions.remove(action)

    def _notify_actions(self):
        from gi.repository import GLib
        # Always dispatch UI updates on the GTK main thread
        GLib.idle_add(self._notify_actions_gtk)

    def _notify_actions_gtk(self):
        for action in list(self._registered_actions):
            try:
                action.on_sinks_updated()
            except Exception:
                pass
        return False  # Don't repeat

    def __del__(self):
        self._stop_polling.set()
