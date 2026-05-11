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

# Sentinel key used for the master system-sound sink entry
MASTER_SINK_KEY = "__master__"


class _PinnedPlaceholder:
    """Represents a pinned app that is currently not running."""
    def __init__(self, raw_key: str, plugin):
        self._raw_key = raw_key
        self._plugin = plugin
        self.mute = False
        self.index = -1
        self.proplist: dict = {}

    def display_name(self) -> str:
        if self._raw_key == MASTER_SINK_KEY:
            return "System"
        overrides = self._plugin.get_display_name_overrides()
        if self._raw_key in overrides:
            return overrides[self._raw_key]
        # Key is "appname|binary" — use binary part as default display
        parts = self._raw_key.split("|", 1)
        binary = parts[1] if len(parts) == 2 and parts[1] else parts[0]
        return BetterVolumeMixer.KNOWN_BINARY_ALIASES.get(binary, binary)


class _MasterSink:
    """Wraps a PulseAudio sink (output device) to look like a sink-input."""
    def __init__(self, sink):
        self._sink = sink
        self.mute = sink.mute
        self.index = sink.index
        self.proplist: dict = {"application.name": "System", "application.process.binary": ""}

    @property
    def raw_sink(self):
        return self._sink


class BetterVolumeMixer(PluginBase):
    # Maps binary name → nice display name
    KNOWN_BINARY_ALIASES: dict[str, str] = {
        "discord":          "Discord",
        "spotify":          "Spotify",
        "slack":            "Slack",
        "teams":            "MS Teams",
        "zoom":             "Zoom",
        "telegram-desktop": "Telegram",
        "thunderbird":      "Thunderbird",
        "firefox":          "Firefox",
        "vivaldi":          "Vivaldi",
        "brave-browser":    "Brave",
        "signal-desktop":   "Signal",
        "obs":              "OBS",
        "vlc":              "VLC",
        "mpv":              "mpv",
        "steam":            "Steam",
        "chromium":         "Chromium",
        "google-chrome":    "Chrome",
        "chrome":           "Chrome",
    }

    def __init__(self):
        super().__init__()

        self.pulse = pulsectl.Pulse("volume-mixer-pro", threading_lock=True)
        self.active_sinks: list = []
        self.page_offset: int = 0
        self._volume_cache: dict[str, int] = {}  # raw_key -> last known volume %
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
        # Master sink is always in the priority list by default
        return {
            "priority_list": [MASTER_SINK_KEY],
            "hidden_list": [],
            "pinned_list": [MASTER_SINK_KEY],
            "display_name_overrides": {},
            "custom_icons": {},
        }

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

    def get_pinned_list(self) -> list[str]:
        return self._plugin_settings.get("pinned_list", [])

    def set_pinned_list(self, lst: list[str]):
        self._plugin_settings["pinned_list"] = lst
        self.save_plugin_settings()

    def get_display_name_overrides(self) -> dict[str, str]:
        return self._plugin_settings.get("display_name_overrides", {})

    def set_display_name_overrides(self, d: dict[str, str]):
        self._plugin_settings["display_name_overrides"] = d
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

    def _make_sink_key(self, sink) -> str:
        """Composite key: 'application.name|binary'. Falls back gracefully."""
        p = sink.proplist
        app_name = p.get("application.name", "") or ""
        binary   = p.get("application.process.binary", "") or ""
        return f"{app_name}|{binary}"

    def _refresh_sinks(self):
        try:
            all_inputs = self.pulse.sink_input_list()
            all_sinks  = self.pulse.sink_list()
        except Exception:
            return

        hidden   = self.get_hidden_list()
        priority = self.get_priority_list()
        pinned   = self.get_pinned_list()

        # Ensure master sink entry exists in priority list
        if MASTER_SINK_KEY not in priority and MASTER_SINK_KEY not in hidden:
            priority.insert(0, MASTER_SINK_KEY)
            self.set_priority_list(priority)

        # Auto-register newly seen sink-inputs
        known = set(priority + hidden)
        changed = False
        for s in all_inputs:
            key = self._make_sink_key(s)
            if key and key not in known:
                priority.append(key)
                known.add(key)
                changed = True
        if changed:
            self.set_priority_list(priority)

        # Build lookup of running sink-inputs keyed by composite key
        running: dict[str, object] = {}
        for s in all_inputs:
            key = self._make_sink_key(s)
            if key not in running:
                running[key] = s

        # Pick the default output sink (active playback device)
        try:
            default_name = self.pulse.server_info().default_sink_name
            master_sink = next((s for s in all_sinks if s.name == default_name), None)
        except Exception:
            master_sink = None
        if master_sink is None and all_sinks:
            master_sink = all_sinks[0]  # fallback

        # Cache current volumes of all running sinks
        for key, s in running.items():
            try:
                self._volume_cache[key] = round(self.pulse.volume_get_all_chans(s) * 100)
            except Exception:
                pass
        # Also cache master sink volume
        if master_sink is not None:
            try:
                self._volume_cache[MASTER_SINK_KEY] = round(self.pulse.volume_get_all_chans(master_sink) * 100)
            except Exception:
                pass

        # Build final ordered list respecting priority order.
        # Pinned entries always appear (placeholder if not running).
        # Non-pinned entries only appear when actually running.
        result = []
        seen_keys = set()

        for key in priority:
            if key in hidden:
                continue
            if key == MASTER_SINK_KEY:
                entry = _MasterSink(master_sink) if master_sink else _PinnedPlaceholder(key, self)
                result.append(entry)
                seen_keys.add(key)
            elif key in pinned:
                entry = running[key] if key in running else _PinnedPlaceholder(key, self)
                result.append(entry)
                seen_keys.add(key)
            elif key in running:
                result.append(running[key])
                seen_keys.add(key)

        # Append any running sinks not yet in priority list (newly detected, not yet saved)
        for key, sink in running.items():
            if key not in seen_keys and key not in hidden:
                result.append(sink)

        self.active_sinks = result

        max_offset = max(0, (len(self.active_sinks) - 1) // SLOTS_PER_PAGE)
        if self.page_offset > max_offset:
            self.page_offset = max_offset

        self._notify_actions()

    # ── Name/icon helpers ─────────────────────────────────────────────────

    def _app_raw_key(self, sink) -> str:
        """Internal composite key for the sink."""
        if isinstance(sink, _PinnedPlaceholder):
            return sink._raw_key
        if isinstance(sink, _MasterSink):
            return MASTER_SINK_KEY
        return self._make_sink_key(sink)

    def _app_name(self, sink) -> str:
        """Display name: user override → binary alias → binary → app name."""
        if isinstance(sink, _PinnedPlaceholder):
            return sink.display_name()
        if isinstance(sink, _MasterSink):
            key = MASTER_SINK_KEY
            overrides = self.get_display_name_overrides()
            return overrides.get(key, "System")

        key = self._app_raw_key(sink)
        overrides = self.get_display_name_overrides()
        if key in overrides:
            return overrides[key]

        p = sink.proplist
        binary = p.get("application.process.binary", "") or ""
        if binary:
            return self.KNOWN_BINARY_ALIASES.get(binary, binary)
        return p.get("application.name", "") or "Unknown"

    def _app_icon_name(self, sink) -> str:
        if isinstance(sink, (_PinnedPlaceholder, _MasterSink)):
            return ""
        return sink.proplist.get("application.icon_name", "")

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
        if isinstance(sink, _PinnedPlaceholder):
            return self._volume_cache.get(sink._raw_key)
        try:
            if isinstance(sink, _MasterSink):
                vol = round(self.pulse.volume_get_all_chans(sink.raw_sink) * 100)
            else:
                vol = round(self.pulse.volume_get_all_chans(sink) * 100)
            self._volume_cache[self._app_raw_key(sink)] = vol
            return vol
        except Exception:
            return self._volume_cache.get(self._app_raw_key(sink))

    def change_volume(self, slot: int, delta: float):
        sink = self.get_sink_for_slot(slot)
        if sink is None or isinstance(sink, _PinnedPlaceholder):
            return
        try:
            if isinstance(sink, _MasterSink):
                vol = self.pulse.volume_get_all_chans(sink.raw_sink)
                self.pulse.volume_set_all_chans(sink.raw_sink, max(0.0, min(1.5, vol + delta)))
            else:
                vol = self.pulse.volume_get_all_chans(sink)
                self.pulse.volume_set_all_chans(sink, max(0.0, min(1.5, vol + delta)))
            self._notify_actions()
        except Exception:
            pass

    def toggle_mute(self, slot: int):
        sink = self.get_sink_for_slot(slot)
        if sink is None or isinstance(sink, _PinnedPlaceholder):
            return
        try:
            if isinstance(sink, _MasterSink):
                rs = sink.raw_sink
                self.pulse.sink_mute(rs.index, not rs.mute)
            else:
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
        GLib.idle_add(self._notify_actions_gtk)

    def _notify_actions_gtk(self):
        for action in list(self._registered_actions):
            try:
                action.on_sinks_updated()
            except Exception:
                pass
        return False

    def __del__(self):
        self._stop_polling.set()
