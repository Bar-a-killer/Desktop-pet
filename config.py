import yaml
from pathlib import Path

_cfg = None

def get() -> dict:
    global _cfg
    if _cfg is None:
        path = Path(__file__).parent / "config.yaml"
        with open(path, "r") as f:
            _cfg = yaml.safe_load(f)
    return _cfg

def physics() -> dict:
    return get()["physics"]

def pet() -> dict:
    return get()["pet"]

def launch() -> dict:
    return get()["launch"]

def timers() -> dict:
    return get()["timers"]
