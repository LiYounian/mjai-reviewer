"""统一配置：data_dir 在哪、profile 在哪。

config.json 在项目根（gitignore），结构:
  {
    "data_dir": "/Users/yqg/MajData"   # 可选，默认 <project_root>/data
  }

约定:
  data_dir/games/   天凤 json (喂下游 mjai-reviewer/NAGA)
  data_dir/raw/     雀魂中间态 json (kbkn3 decoder 输出)
  data_dir/profile/ Playwright 持久化登录态 (chmod 700)

读 config 是 lazy：每次调 get_data_dir() 都重读，server 可热更新；
CLI 里也是每次调用都读到最新。
"""
from __future__ import annotations
import json
import os
import stat
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.json"
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


def get_data_dir() -> Path:
    """读当前 config 里的 data_dir；未设则用项目根下 ./data。

    支持 ~ 展开和环境变量。返回绝对路径。
    """
    cfg = load_config()
    raw = cfg.get("data_dir", "").strip()
    if not raw:
        return DEFAULT_DATA_DIR
    expanded = os.path.expanduser(os.path.expandvars(raw))
    p = Path(expanded)
    if not p.is_absolute():
        # 相对路径相对于项目根（朋友粘个 "myData" 这种也合理）
        p = PROJECT_ROOT / p
    return p.resolve()


def get_games_dir() -> Path:
    return get_data_dir() / "games"


def get_raw_dir() -> Path:
    return get_data_dir() / "raw"


def get_profile_dir() -> Path:
    return get_data_dir() / "profile"


def ensure_dirs() -> None:
    """让所有子目录都存在；profile 强制 chmod 700。"""
    games = get_games_dir()
    raw = get_raw_dir()
    profile = get_profile_dir()
    for d in (games, raw, profile):
        d.mkdir(parents=True, exist_ok=True)
    os.chmod(profile, stat.S_IRWXU)


def set_data_dir(path: str) -> Path:
    """更新 config 里的 data_dir 并立即建好子目录。返回展开后的绝对路径。"""
    cfg = load_config()
    cfg["data_dir"] = path
    save_config(cfg)
    ensure_dirs()
    return get_data_dir()
