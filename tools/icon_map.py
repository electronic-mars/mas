"""Which Hugeicons icon stands behind each of our names.

The icon names are keys: they are written into the device config and the
auto-matching runs on them. That is why all of the old twenty-four names are
kept, even if the drawing behind them changed completely. New names are only
ever added.

Set: @hugeicons/core-free-icons, MIT licence.
"""

# Our twenty-four names. The order is the one used in the picker palette.
DEVICES = {
    # sound
    "speakers": "Speaker01",
    "edifier-r1700bts": "Speaker",
    "soundbar": "MonitorSpeaker",
    "jbl-charge": "Radio",
    "marshall-emberton-ii": "BoomBox",
    "homepod-mini": "Home01",
    "sonos-era-100": "GoogleHome",
    # screens and machines
    "tv": "ModernTv",
    "monitor": "Computer",
    "laptop": "Laptop",
    "thinkpad": "LaptopCloud",
    "alienware-m18-r2": "Alien01",
    # worn on the head
    "headphones": "Headphones",
    "headset": "Headset",
    "hyperx-cloud": "CustomerService01",
    "earbuds": "Airpod02",
    "galaxy-buds": "Airpod03",
    "sony-xm5": "Crown03",
    "razer-kraken": "Evil",
    "powerbeats-pro-2": "EnergyEllipse",
    # input and ports
    "microphone": "Mic01",
    "hdmi": "HdmiPort",
    "usb": "Usb",
    "bluetooth": "Bluetooth",
}

# Added marks: set by hand from the palette for devices whose portrait is not
# readable anyway. They differ at a glance — that is the point.
MARKS = {
    "mark-cat": "Cat",
    "mark-clover": "Clover",
    "mark-duck": "RubberDuck",
    "mark-wink": "TongueWinkLeft",
    "mark-ghost": "Ghost",
    "mark-skull": "Skull",
    "mark-reactor": "NuclearPower",
    "mark-brain": "AiBrain01",
    "mark-gamepad": "Gamepad",
    "mark-joystick": "GameController03",
    "mark-nintendo": "Nintendo",
    "mark-spotify": "Spotify",
    "mark-vr": "VirtualRealityVr01",
    "mark-ipod": "Ipod",
    "mark-cassette": "CassetteTape",
    "mark-nfc": "Nfc",
    # Separate names at the owner's request: the same artwork is also available
    # under a device name, but picking by meaning is clearer in the palette.
    "mark-crown": "Crown03",
    "speaker-desk": "MonitorSpeaker",
    "speaker-radio": "Radio",
    "mark-bird": "Bird",
}

# Interface icons: settings sections, tabs, volume, utility rows.
UI = {
    "tab-devices": "Speaker01",
    "tab-mixer": "SlidersHorizontal",
    "tab-settings": "Cog",
    "tab-about": "InformationCircle",
    "sec-startup": "Rocket01",
    "sec-auto": "Transmission",
    "sec-control": "Ds3Tool",
    "sec-switching": "ArrowDataTransferHorizontal",
    "sec-appearance": "PaintBoard",
    "sec-diag": "Bug01",
    "vol-low": "VolumeLow",
    "vol-mid": "VolumeUp",
    "vol-high": "VolumeHigh",
    "vol-off": "VolumeOff",
    "vol-mute": "VolumeMute01",
    "ui-bell": "BellRing",
    "ui-keyboard": "Keyboard",
    "ui-globe": "Globe",
    "ui-moon": "Moon02",
    "ui-sun": "Sun03",
    "ui-folder": "FolderOpen",
    "ui-github": "Github",
    "ui-tag": "Tag01",
    "ui-power": "PowerService",
    "ui-mic": "Mic01",
    "ui-wave": "AudioWave01",
    # List headings and the buttons on the "about" tab.
    "ui-cursor": "Cursor01",
    "ui-toggle": "ToggleOn",
    "ui-apps": "Grid2X2",
    "ui-heart": "FavouriteCircle",
    "ui-refresh": "Refresh01",
    "ui-exit": "Logout01",
}

ALL = {**DEVICES, **MARKS, **UI}
