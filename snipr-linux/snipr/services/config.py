"""JSON-backed user config for Snipr."""

from __future__ import annotations

import json
import os
from pathlib import Path


CONFIG_DIR = (
    Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    / "snipr"
)
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULTS: dict = {
    # Accelerator string parsed by Gtk.accelerator_parse, e.g. "Print",
    # "<Ctrl><Shift>s", "<Super>a". Empty string disables the global hotkey.
    "global_hotkey": "",
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_FILE) as f:
            data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return cfg


def save(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_FILE)
