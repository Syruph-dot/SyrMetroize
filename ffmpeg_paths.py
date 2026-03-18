"""
Centralized FFmpeg path policy.

Only bundled executables are allowed:
- syrmetroize/ffmpeg/ffmpeg.exe
- syrmetroize/ffmpeg0.6/ffmpeg.exe
"""
import os
from typing import Optional, Tuple


def _bundle_paths() -> Tuple[str, str]:
    package_dir = os.path.dirname(os.path.abspath(__file__))
    modern = os.path.abspath(os.path.join(package_dir, "ffmpeg", "ffmpeg.exe"))
    legacy = os.path.abspath(os.path.join(package_dir, "ffmpeg0.6", "ffmpeg.exe"))
    return modern, legacy


def get_bundled_ffmpeg_paths() -> Tuple[Optional[str], Optional[str]]:
    modern, legacy = _bundle_paths()
    modern_path = modern if os.path.exists(modern) else None
    legacy_path = legacy if os.path.exists(legacy) else None
    return modern_path, legacy_path


def _normalize(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def is_allowed_bundled_ffmpeg(path: str) -> bool:
    if not path:
        return False
    modern, legacy = _bundle_paths()
    candidate = _normalize(path)
    return candidate in {_normalize(modern), _normalize(legacy)}


def resolve_ffmpeg_path(requested_path: Optional[str] = None) -> str:
    modern_path, legacy_path = get_bundled_ffmpeg_paths()

    if requested_path and requested_path.strip().lower() not in {"ffmpeg", "ffmpeg.exe"}:
        if not is_allowed_bundled_ffmpeg(requested_path):
            raise ValueError(
                "FFmpeg path is restricted to bundled executables: "
                "syrmetroize/ffmpeg/ffmpeg.exe or syrmetroize/ffmpeg0.6/ffmpeg.exe"
            )
        resolved = os.path.abspath(requested_path)
        if not os.path.exists(resolved):
            raise FileNotFoundError(f"Bundled FFmpeg not found: {resolved}")
        return resolved

    if modern_path:
        return modern_path
    if legacy_path:
        return legacy_path

    raise FileNotFoundError(
        "No bundled FFmpeg executable found. Expected one of: "
        "syrmetroize/ffmpeg/ffmpeg.exe, syrmetroize/ffmpeg0.6/ffmpeg.exe"
    )
