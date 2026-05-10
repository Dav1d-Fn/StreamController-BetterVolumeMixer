# Better Volume Mixer

A per-app volume mixer plugin for [StreamController](https://github.com/StreamController/StreamController). Control the volume of individual applications directly from your Stream Deck — with priority sorting, custom icons, page navigation, and live volume display.

> **Optimized for the Stream Deck MK.2 (3×5).** Individual actions work on any model.

---

![Demo](assets/BetterVolumeMixerPreview.mp4)

---

## Features

- **Per-app volume control** — Volume Up / Down buttons per active audio app
- **Live display** — App icon, name, and current volume on the middle button
- **Priority list** — Define which apps appear first; reorder, hide unwanted apps
- **Custom icons** — Override auto-detected icons for any app (e.g. Spotify)
- **Page navigation** — Scroll through more than 4 active apps
- **Auto-hide nav** — Navigation hides itself when there's only one page
- **Configurable labels** — Choose what's shown on top/center/bottom of every button
- **Settings sync** — Change one Volume Up button, sync to all columns automatically
- **Export / Import** — Back up and restore your full configuration as a ZIP

---

## Requirements

- [StreamController](https://github.com/StreamController/StreamController)
- Python package `pulsectl`:

```bash
pip install pulsectl --break-system-packages
```

---

## Installation

1. Go to [Releases](https://github.com/dav1d-fn/BetterVolumeMixer/releases) and download the latest `com_dav1dfn_BetterVolumeMixer.zip`
2. Extract the ZIP — you'll get a folder called `com_dav1dfn_BetterVolumeMixer`
3. Copy it into your StreamController plugins folder:

```bash
cp -r com_dav1dfn_BetterVolumeMixer \
  ~/.var/app/com.core447.StreamController/data/plugins/
```

4. Restart StreamController

> For native (non-Flatpak) installs the plugins folder may be at  
> `~/.local/share/StreamController/plugins/`

---

## Setup

The plugin ships with a pre-built **Better Volume Mixer** page. Place the **Open Mixer** action anywhere on your main page — pressing it switches to the mixer.

### Recommended MK.2 layout (3 rows × 5 columns)

```
[ Back         ]  [ Vol ▲  ]  [ Vol ▲  ]  [ Vol ▲  ]  [ Vol ▲  ]
[ Next →       ]  [ App    ]  [ App    ]  [ App    ]  [ App    ]
[ ← Prev       ]  [ Vol ▼  ]  [ Vol ▼  ]  [ Vol ▼  ]  [ Vol ▼  ]
  Navigation       Slot 0      Slot 1      Slot 2      Slot 3
```

<!-- Replace with your own screenshot -->
![Mixer page layout](assets/layout.png)

---

## Actions

| Action | Description |
|--------|-------------|
| **Open Mixer** | Opens the mixer page. Place on your main page. |
| **Nav: Back** | Returns to your main page. |
| **Nav: Next →** | Shows the next 4 apps. |
| **Nav: ← Prev** | Shows the previous 4 apps. |
| **Volume Up** | Increases volume for the app in this column. |
| **Volume Down** | Decreases volume for the app in this column. |
| **App Display** | Shows app icon, name, volume. Click to mute/unmute. |

---

## Configuration

### Volume Up / Down
| Setting | Description |
|---------|-------------|
| Column Slot (0–3) | Which app column this button controls |
| Volume Step (%) | How much to change volume per press (default 5%) |
| Top / Center / Bottom | Volume %, App Name, or Custom Text |
| Custom Icon | PNG, SVG, or GIF for the button |
| Sync settings | Apply to all Volume Up (or Down) buttons at once |

### App Display
| Setting | Description |
|---------|-------------|
| Column Slot (0–3) | Which app column this shows |
| Show App Icon | Toggle automatic icon |
| Top / Center / Bottom | App Name, Volume %, or Custom Text |
| Sync settings | Apply to all App Display buttons |
| App Priority List | Order apps appear in columns; 🖼 sets a custom icon |
| Hidden Apps | Apps that are never shown in the mixer |

### Navigation buttons
| Setting | Description |
|---------|-------------|
| Custom Icon | PNG, SVG, or GIF |
| Top / Center / Bottom | Page Number or Custom Text |
| Hide if only one page | Hides the button when there's nothing to navigate |

### Open Mixer — Export / Import
Open the settings of the **Open Mixer** button and scroll to the bottom:

- **Export Settings…** — saves priority list, hidden apps, custom icons, and all pages to a ZIP
- **Import Settings…** — restores a previously exported ZIP (requires StreamController restart)

---

## Custom Icons

Better Volume Mixer detects app icons automatically via GTK's icon theme. For apps where this doesn't work (e.g. Spotify via Flatpak):

1. Open any **App Display** button settings
2. In **App Priority List**, click 🖼 next to the app name
3. Browse to a PNG or SVG and click **Set Icon**

---

## License

[GPL-3.0](LICENSE)
