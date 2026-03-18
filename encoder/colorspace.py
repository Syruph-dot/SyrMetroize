"""
色彩空间处理器 - 使用 FFmpeg 滤镜模拟 Flash 播放器的 BT.601/BT.709 偏差。

说明：
- 本模块仅使用 FFmpeg，不依赖 OpenCV/NumPy。
- ERROR_MAPPING 模式优先尝试 colormatrix/colorspace 进行矩阵映射。
- SIMULATION 模式使用 eq 滤镜进行近似观感调整。
"""
import os
import shutil
import subprocess
from typing import Callable, List, Optional


def _discover_ffmpeg_path(preferred_path: Optional[str] = None) -> Optional[str]:
    candidates = []
    if preferred_path:
        candidates.append(preferred_path)

    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates.append(os.path.join(package_dir, "ffmpeg", "ffmpeg.exe"))
    candidates.append(os.path.join(package_dir, "ffmpeg0.6", "ffmpeg.exe"))

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        candidates.append(system_ffmpeg)

    for path in candidates:
        if path and os.path.exists(path):
            return path

    return None


def _build_ffmpeg_filter_candidates(
    mode: str,
    saturation: float,
    contrast: float,
    gamma: float,
) -> List[str]:
    if mode == "simulation":
        sat_val = 1.0 + saturation
        con_val = 1.0 + contrast
        gamma_val = 1.0 + gamma
        return [f"eq=saturation={sat_val}:contrast={con_val}:gamma={gamma_val}"]

    # 兼容不同 FFmpeg 版本（新旧版本对滤镜名和参数支持不同）。
    return [
        "colormatrix=bt709:bt601",
        "colorspace=all=bt709:iall=bt601-6-625:fast=1",
        "colorspace=all=bt709:iall=bt601-6-525:fast=1",
    ]


def _run_ffmpeg_color_filter(
    ffmpeg_path: str,
    input_path: str,
    output_path: str,
    vf: str,
) -> tuple:
    cmd = [
        ffmpeg_path,
        "-nostdin",
        "-y",
        "-i",
        input_path,
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        output = (result.stdout or "") + (result.stderr or "")
        return result.returncode == 0, output
    except Exception as e:
        return False, str(e)


def process_color_space(
    input_path: str,
    output_path: str,
    mode: str = "simulation",
    saturation: float = -0.08,
    contrast: float = 0.03,
    gamma: float = 0.02,
    progress_callback: Optional[Callable[[float], None]] = None,
    ffmpeg_path: Optional[str] = None,
) -> bool:
    resolved_ffmpeg = _discover_ffmpeg_path(ffmpeg_path)
    if not resolved_ffmpeg:
        print("[Color Space] FFmpeg backend unavailable; preserving original stream")
        if input_path != output_path:
            shutil.copy(input_path, output_path)
        if progress_callback:
            progress_callback(1.0)
        return True

    filter_candidates = _build_ffmpeg_filter_candidates(mode, saturation, contrast, gamma)
    last_error = ""

    for vf in filter_candidates:
        print(f"[Color Space] Trying FFmpeg backend: {resolved_ffmpeg} with vf='{vf}'")
        ok, output = _run_ffmpeg_color_filter(resolved_ffmpeg, input_path, output_path, vf)
        if ok:
            if progress_callback:
                progress_callback(1.0)
            return True

        last_error = output
        lowered = output.lower()
        if "no such filter" in lowered or "option not found" in lowered or "invalid argument" in lowered:
            print("[Color Space] FFmpeg filter unsupported, trying fallback filter expression")
            continue

        print("[Color Space] FFmpeg backend failed, trying next fallback path")
        break

    if last_error:
        print("[Color Space] FFmpeg backend failed; preserving original stream")
        print(last_error[-800:])

    if input_path != output_path:
        shutil.copy(input_path, output_path)
    if progress_callback:
        progress_callback(1.0)
    return True
