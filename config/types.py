"""
配置数据类定义
"""
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class VideoProfile(Enum):
    BASELINE = "baseline"
    MAIN = "main"
    HIGH = "high"


class ResolutionPreset(Enum):
    P240 = "240p"
    P360 = "360p"
    P480 = "480p"
    P720 = "720p"


class AudioCodec(Enum):
    HE_AAC_V1 = "he-aac"
    AAC_LC = "aac-lc"


class EncodeMode(Enum):
    ONE_PASS_ABR = "1pass"
    TWO_PASS_VBR = "2pass"


class ContainerFormat(Enum):
    FLV = "flv"
    MP4 = "mp4"


class TransportProtocol(Enum):
    RTMP = "rtmp"
    HLS = "hls"
    HTTP_PROGRESSIVE = "http"


class DeinterlaceMethod(Enum):
    YADIF = "yadif"
    BOB = "yadif=1"
    DISCARD = "discard"


class ColorSpaceMode(Enum):
    NONE = "none"
    ERROR_MAPPING = "error_mapping"
    SIMULATION = "simulation"


@dataclass
class PreprocessConfig:
    enabled: bool = False
    denoise_enabled: bool = False
    denoise_strength: float = 4.0
    deinterlace_enabled: bool = False
    deinterlace_method: DeinterlaceMethod = DeinterlaceMethod.YADIF
    sharpen_enabled: bool = False
    sharpen_strength: float = 1.0
    contrast_enabled: bool = False
    contrast_value: float = 1.0
    saturation_enabled: bool = False
    saturation_value: float = 1.0
    scale_enabled: bool = False
    scale_resolution: Optional[ResolutionPreset] = None
    custom_width: Optional[int] = None
    custom_height: Optional[int] = None


@dataclass
class VideoConfig:
    enabled: bool = True
    profile: VideoProfile = VideoProfile.MAIN
    resolution: ResolutionPreset = ResolutionPreset.P360
    encode_mode: EncodeMode = EncodeMode.ONE_PASS_ABR
    bitrate: int = 600
    max_bitrate: int = 900
    keyint: int = 100
    vbv_maxrate: int = 1100
    vbv_bufsize: int = 2000
    bframes: int = 2
    ref_frames: int = 3
    subme: int = 6
    me_method: str = "hex"
    deblock: str = "-1:-1"


@dataclass
class AudioConfig:
    enabled: bool = True
    codec: AudioCodec = AudioCodec.AAC_LC
    bitrate: int = 96
    sample_rate: int = 44100
    ms_stereo: bool = True
    side_channel_reduce_db: float = 0.0
    dynamic_compression_ratio: float = 1.0
    loudness_target_lufs: float = -16.0
    high_pass_filter: bool = False


@dataclass
class DoubleEncodeConfig:
    enabled: bool = False
    first_pass_resolution: ResolutionPreset = ResolutionPreset.P360


@dataclass
class ColorSpaceConfig:
    mode: ColorSpaceMode = ColorSpaceMode.NONE
    auto_apply_legacy_flash_simulation: bool = True
    saturation_adjust: float = -0.08
    contrast_adjust: float = 0.03
    gamma_adjust: float = 0.02


@dataclass
class EffectsConfig:
    preprocess: PreprocessConfig = field(default_factory=PreprocessConfig)
    double_encode: DoubleEncodeConfig = field(default_factory=DoubleEncodeConfig)
    color_space: ColorSpaceConfig = field(default_factory=ColorSpaceConfig)


@dataclass
class EncodingConfig:
    video: VideoConfig = field(default_factory=VideoConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    effects: EffectsConfig = field(default_factory=EffectsConfig)
    container: ContainerFormat = ContainerFormat.MP4
    transport: TransportProtocol = TransportProtocol.HTTP_PROGRESSIVE
    rtmp_publish_url: str = "rtmp://localhost/live/syrmetroize"
    hls_playlist_path: Optional[str] = None


@dataclass
class PresetConfig:
    name: str
    description: str
    config: EncodingConfig


RESOLUTION_MAP = {
    ResolutionPreset.P240: (320, 240),
    ResolutionPreset.P360: (640, 360),
    ResolutionPreset.P480: (854, 480),
    ResolutionPreset.P720: (1280, 720),
}


def get_resolution_dimensions(resolution: ResolutionPreset) -> tuple:
    return RESOLUTION_MAP.get(resolution, (640, 360))
