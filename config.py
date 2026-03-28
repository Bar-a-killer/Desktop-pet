import yaml
from pathlib import Path
from functools import lru_cache

@lru_cache(maxsize=1)
def get() -> dict:
    path = Path(__file__).parent / "config.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)

def physics() -> dict:
    return get()["physics"]

def pet() -> dict:
    return get()["pet"]

def launch() -> dict:
    return get()["launch"]

def timers() -> dict:
    return get()["timers"]
