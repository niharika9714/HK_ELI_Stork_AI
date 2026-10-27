import importlib
import os
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def load_config(path=None):
    target = Path(path or os.getenv('HKELI_CONFIG', ROOT / 'config.local.toml'))
    if not target.exists():
        target = ROOT / 'config.example.toml'
    with target.open('rb') as stream:
        config = tomllib.load(stream)
    if config['app']['mode'] not in ('demo', 'live'):
        raise ValueError('app.mode must be demo or live')
    return config


def plugin(name):
    module, function = name.split(':', 1)
    return getattr(importlib.import_module(module), function)
