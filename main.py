#!/usr/bin/env python3
"""
SyrMetroize - 2010年代流媒体视频编码器
主入口文件
"""
import os
import sys
import argparse

from ffmpeg_paths import resolve_ffmpeg_path

_package_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_package_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)


def get_default_ffmpeg_path() -> str:
    return resolve_ffmpeg_path()


def main():
    parser = argparse.ArgumentParser(
        description="SyrMetroize"
    )
    parser.add_argument(
        "--ffmpeg",
        type=str,
        default=None,
        help="FFmpeg可执行文件路径"
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="使用命令行模式"
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        help="输入视频文件"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="输出视频文件"
    )
    parser.add_argument(
        "-p", "--preset",
        type=str,
        choices=["smooth", "standard", "standard_480p", "hd"],
        help="预设配置"
    )
    parser.add_argument(
        "--double-encode",
        action="store_true",
        help="启用双编码"
    )
    parser.add_argument(
            "--color-space",
            type=str,
            choices=["none", "error_mapping", "simulation"],
            default="none",
            help="色彩空间处理模式: none(无), error_mapping(错误映射), simulation(模拟)"
        )
    parser.add_argument(
        "--disable-auto-legacy-color",
        action="store_true",
        help="禁用在 FLV + 480P及以下场景自动启用色彩模拟"
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["rtmp", "hls", "http"],
        help="传输协议: rtmp, hls, http"
    )
    parser.add_argument(
        "--rtmp-url",
        type=str,
        help="RTMP 推流目标地址 (例如 rtmp://localhost/live/stream)"
    )
    parser.add_argument(
        "--hls-output",
        type=str,
        help="HLS 输出路径 (可为 .m3u8 文件路径或目录路径)"
    )
    
    args = parser.parse_args()
    
    try:
        ffmpeg_path = resolve_ffmpeg_path(args.ffmpeg)
    except Exception as e:
        print(f"FFmpeg path error: {e}", file=sys.stderr)
        return 2
    
    if args.cli:
        from syrmetroize.config.presets import get_preset
        from syrmetroize.encoder.pipeline import EncodingPipeline
        
        if not args.input or not args.output:
            parser.error("CLI模式需要指定输入和输出文件")
        
        config = None
        if args.preset:
            preset = get_preset(args.preset)
            if preset:
                config = preset.config
        
        if config is None:
            from syrmetroize.config.types import EncodingConfig
            config = EncodingConfig()
        
        if args.double_encode:
            config.effects.double_encode.enabled = True
        
        if args.color_space:
            from syrmetroize.config.types import ColorSpaceMode
            config.effects.color_space.mode = ColorSpaceMode(args.color_space)

        if args.disable_auto_legacy_color:
            config.effects.color_space.auto_apply_legacy_flash_simulation = False

        if args.transport:
            from syrmetroize.config.types import TransportProtocol
            config.transport = TransportProtocol(args.transport)

        if args.rtmp_url:
            config.rtmp_publish_url = args.rtmp_url

        if args.hls_output:
            config.hls_playlist_path = args.hls_output
        
        def progress_callback(step, progress):
            print(f"\r{step}: {progress*100:.1f}%", end="", flush=True)
        
        def error_callback(error):
            print(f"\n错误: {error}", file=sys.stderr)
        
        pipeline = EncodingPipeline(
            ffmpeg_path=ffmpeg_path,
            progress_callback=progress_callback,
            error_callback=error_callback
        )
        
        print(f"输入: {args.input}")
        print(f"输出: {args.output}")
        print(f"FFmpeg: {ffmpeg_path}")
        if config.transport.value == "rtmp":
            print(f"RTMP 目标: {config.rtmp_publish_url}")
        if config.transport.value == "hls" and config.hls_playlist_path:
            print(f"HLS 输出: {config.hls_playlist_path}")
        print("开始编码...")
        
        success = pipeline.encode(args.input, args.output, config)
        
        if success:
            print("\n编码完成!")
            return 0
        else:
            print("\n编码失败!")
            return 1
    else:
        from syrmetroize.gui import MainWindow
        
        app = MainWindow(ffmpeg_path=ffmpeg_path)
        app.run()
        return 0


if __name__ == "__main__":
    sys.exit(main())
