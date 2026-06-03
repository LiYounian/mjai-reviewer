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
import sys
from pathlib import Path

# 区分两个路径概念：
#   RESOURCE_ROOT — 静态资源所在地（viewer.html / inject.js）
#                   开发时 = 项目根；frozen 时 = sys._MEIPASS（PyInstaller 解压目录）
#   USER_DATA_ROOT — 用户数据落盘根（config.json / data/）
#                   开发时 = 项目根；frozen 时 = ~/.mjai-tool/（不能写进 app 包，只读）
_FROZEN = getattr(sys, "frozen", False)
PROJECT_ROOT = Path(__file__).resolve().parent.parent  # 兼容旧代码

if _FROZEN:
    # PyInstaller onedir: 资源在 _MEIPASS 旁的 _internal 里
    RESOURCE_ROOT = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    USER_DATA_ROOT = Path.home() / ".mjai-tool"
else:
    RESOURCE_ROOT = PROJECT_ROOT
    USER_DATA_ROOT = PROJECT_ROOT

CONFIG_PATH = USER_DATA_ROOT / "config.json"
DEFAULT_DATA_DIR = USER_DATA_ROOT / "data"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
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
        # 相对路径相对于用户数据根（朋友粘个 "myData" 这种也合理）
        p = USER_DATA_ROOT / p
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
