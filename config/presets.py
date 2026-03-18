"""
预设配置定义
"""
from .types import (
    PresetConfig, EncodingConfig, VideoConfig, AudioConfig,
    EffectsConfig, PreprocessConfig, DoubleEncodeConfig, ColorSpaceConfig,
    VideoProfile, ResolutionPreset, AudioCodec, EncodeMode, ContainerFormat, TransportProtocol
)


PRESETS = {
    "smooth": PresetConfig(
        name="流畅档",
        description="240P, 200-384kbps, Baseline Profile, HE-AAC v1",
        config=EncodingConfig(
            video=VideoConfig(
                profile=VideoProfile.BASELINE,
                resolution=ResolutionPreset.P240,
                bitrate=300,
                max_bitrate=450,
                keyint=60,
                bframes=0,
                ref_frames=1,
            ),
            audio=AudioConfig(
                codec=AudioCodec.HE_AAC_V1,
                bitrate=48,
                sample_rate=22050,
            ),
            container=ContainerFormat.FLV,
            transport=TransportProtocol.HTTP_PROGRESSIVE,
        )
    ),
    "standard": PresetConfig(
        name="标清档",
        description="360P, 500-800kbps, Main Profile, AAC-LC",
        config=EncodingConfig(
            video=VideoConfig(
                profile=VideoProfile.MAIN,
                resolution=ResolutionPreset.P360,
                bitrate=600,
                max_bitrate=900,
                keyint=100,
                bframes=2,
                ref_frames=3,
            ),
            audio=AudioConfig(
                codec=AudioCodec.AAC_LC,
                bitrate=112,
                sample_rate=44100,
            ),
            container=ContainerFormat.FLV,
            transport=TransportProtocol.RTMP,
        )
    ),
    "standard_480p": PresetConfig(
        name="标清档 (480P)",
        description="480P, 700-1000kbps, Main Profile, AAC-LC",
        config=EncodingConfig(
            video=VideoConfig(
                profile=VideoProfile.MAIN,
                resolution=ResolutionPreset.P480,
                bitrate=850,
                max_bitrate=1275,
                keyint=100,
                bframes=2,
                ref_frames=3,
            ),
            audio=AudioConfig(
                codec=AudioCodec.AAC_LC,
                bitrate=128,
                sample_rate=44100,
            ),
            container=ContainerFormat.MP4,
            transport=TransportProtocol.HTTP_PROGRESSIVE,
        )
    ),
    "hd": PresetConfig(
        name="高清档",
        description="720P, 1200-1800kbps, High Profile, AAC-LC",
        config=EncodingConfig(
            video=VideoConfig(
                profile=VideoProfile.HIGH,
                resolution=ResolutionPreset.P720,
                bitrate=1500,
                max_bitrate=2250,
                keyint=150,
                bframes=3,
                ref_frames=4,
            ),
            audio=AudioConfig(
                codec=AudioCodec.AAC_LC,
                bitrate=160,
                sample_rate=44100,
            ),
            container=ContainerFormat.MP4,
            transport=TransportProtocol.HLS,
        )
    ),
}


def get_preset(name: str) -> PresetConfig:
    return PRESETS.get(name)


def get_all_presets() -> dict:
    return PRESETS.copy()
