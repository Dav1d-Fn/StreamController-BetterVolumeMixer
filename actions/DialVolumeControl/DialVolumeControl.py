from src.backend.PluginManager.ActionBase import ActionBase
from src.backend.DeckManagement.InputIdentifier import Input
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw


DEFAULTS = {
    "slot_index":  0,
    "volume_step": 5,
}


class DialVolumeControl(ActionBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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

    def on_removed(self):
        self.plugin_base.unregister_action(self)

    def on_sinks_updated(self):
        pass

    def event_callback(self, event, data=None):
        s = self.get_settings()
        slot = s.get("slot_index", 0)
        step = s.get("volume_step", 5) / 100.0

        if event == Input.Dial.Events.TURN_CW:
            self.plugin_base.change_volume(slot, +step)
        elif event == Input.Dial.Events.TURN_CCW:
            self.plugin_base.change_volume(slot, -step)
        elif event == Input.Dial.Events.SHORT_UP:
            self.plugin_base.toggle_mute(slot)

    # ── Settings UI ───────────────────────────────────────────────────────

    def get_config_rows(self) -> list:
        rows = []

        self.slot_spinner = Adw.SpinRow.new_with_range(0, 3, 1)
        self.slot_spinner.set_title("Volume Slot (0–3)")
        self.slot_spinner.set_subtitle("Which app in the priority list this dial controls")
        rows.append(self.slot_spinner)

        self.step_spinner = Adw.SpinRow.new_with_range(1, 20, 1)
        self.step_spinner.set_title("Volume Step (%)")
        self.step_spinner.set_subtitle("How much each tick changes the volume")
        rows.append(self.step_spinner)

        self._load_config_values()
        self.slot_spinner.connect("changed", self._on_changed)
        self.step_spinner.connect("changed", self._on_changed)
        return rows

    def _load_config_values(self):
        s = self.get_settings()
        self.slot_spinner.set_value(s.get("slot_index", DEFAULTS["slot_index"]))
        self.step_spinner.set_value(s.get("volume_step", DEFAULTS["volume_step"]))

    def _on_changed(self, *args):
        s = self.get_settings()
        s["slot_index"]  = int(self.slot_spinner.get_value())
        s["volume_step"] = int(self.step_spinner.get_value())
        self.set_settings(s)
