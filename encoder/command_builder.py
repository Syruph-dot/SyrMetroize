"""
FFmpeg 命令构建器

视频统一使用 H.264/x264，并将配置中的关键参数映射到实际命令。
音频统一使用 AAC（根据配置选择 LC/HE 配置）。
"""
import os
from typing import List, Optional
from ..config.types import (
    EncodingConfig, VideoConfig, AudioConfig, PreprocessConfig,
    VideoProfile, ResolutionPreset, AudioCodec, EncodeMode,
    ContainerFormat, DeinterlaceMethod, ColorSpaceMode, get_resolution_dimensions
)


class FFmpegCommandBuilder:
    def __init__(self, ffmpeg_path: str, legacy_mode: bool = True):
        self.ffmpeg_path = ffmpeg_path
        self._ffmpeg_dir = os.path.dirname(os.path.abspath(ffmpeg_path))
        self._legacy_mode = legacy_mode
    
    def _get_filter_option(self) -> str:
        if self._legacy_mode:
            return "-vfilters"
        return "-vf"
    
    def _get_audio_filter_option(self) -> str:
        return "-af"
    
    def build_preprocess_filters(self, config: PreprocessConfig) -> List[str]:
        filters = []
        
        if config.denoise_enabled:
            strength = config.denoise_strength
            filters.append(f"hqdn3d={strength}:{strength}")
        
        if config.deinterlace_enabled:
            method = config.deinterlace_method.value
            filters.append(method)
        
        if config.sharpen_enabled:
            strength = config.sharpen_strength
            filters.append(f"unsharp=5:5:{strength}:5:5:{strength}")
        
        if config.contrast_enabled or config.saturation_enabled:
            contrast = config.contrast_value if config.contrast_enabled else 1.0
            saturation = config.saturation_value if config.saturation_enabled else 1.0
            filters.append(f"eq=contrast={contrast}:saturation={saturation}")
        
        if config.scale_enabled:
            if config.custom_width and config.custom_height:
                filters.append(f"scale={config.custom_width}:{config.custom_height}")
            elif config.scale_resolution:
                w, h = get_resolution_dimensions(config.scale_resolution)
                filters.append(f"scale={w}:{h}")
        
        return filters
    
    def build_audio_filters(self, config: AudioConfig) -> List[str]:
        filters = []
        
        if config.side_channel_reduce_db != 0:
            reduce_db = config.side_channel_reduce_db
            filters.append(f"pan=stereo|c0=c0|c1=c1*{10**(-reduce_db/20)}")
        
        if config.dynamic_compression_ratio > 1.0:
            ratio = config.dynamic_compression_ratio
            threshold = 0.25
            filters.append(f"acompressor=threshold={threshold}:ratio={ratio}:attack=20:release=250")
        
        if config.loudness_target_lufs != 0:
            lufs = config.loudness_target_lufs
            filters.append(f"loudnorm=I={lufs}:TP=-1.5:LRA=11")
        
        if config.high_pass_filter:
            filters.append("highpass=f=80")
        
        return filters
    
    def build_video_encoding_params(self, config: VideoConfig, output_format: str = "flv") -> List[str]:
        params = []

        params.extend(["-c:v", "libx264"])
        params.extend(["-profile:v", config.profile.value])
        
        w, h = get_resolution_dimensions(config.resolution)
        params.extend(["-s", f"{w}x{h}"])
        
        params.extend(["-b:v", f"{config.bitrate}k"])
        params.extend(["-maxrate", f"{config.max_bitrate}k"])
        params.extend(["-bufsize", f"{config.vbv_bufsize}k"])
        
        params.extend(["-g", str(config.keyint)])

        params.extend(["-bf", str(config.bframes)])
        params.extend(["-refs", str(config.ref_frames)])
        
        params.extend(["-pix_fmt", "yuv420p"])

        deblock_val = config.deblock.replace(":", ",")
        x264_params = [
            f"subme={config.subme}",
            f"me={config.me_method}",
            f"deblock={deblock_val}",
            f"vbv-maxrate={config.vbv_maxrate}",
            f"vbv-bufsize={config.vbv_bufsize}",
        ]

        if config.profile == VideoProfile.BASELINE:
            x264_params.append("cabac=0")
        else:
            x264_params.append("cabac=1")

        params.extend(["-x264-params", ":".join(x264_params)])
        
        return params
    
    def build_audio_encoding_params(self, config: AudioConfig, output_format: str = "flv", include_filters: bool = True) -> List[str]:
        params = []
        
        audio_filters = self.build_audio_filters(config) if include_filters else []

        params.extend(["-c:a", "aac"])
        if config.codec == AudioCodec.HE_AAC_V1:
            params.extend(["-profile:a", "aac_he"])
        else:
            params.extend(["-profile:a", "aac_low"])

        params.extend(["-b:a", f"{config.bitrate}k"])
        
        params.extend(["-ar", str(config.sample_rate)])
        params.extend(["-ac", "2"])
        
        if audio_filters:
            params.extend([self._get_audio_filter_option(), ",".join(audio_filters)])
        
        return params
    
    def build_color_space_filter(self, mode: ColorSpaceMode, saturation: float, contrast: float, gamma: float) -> Optional[str]:
        if mode == ColorSpaceMode.NONE:
            return None
        
        elif mode == ColorSpaceMode.ERROR_MAPPING:
            return "colorspace=bt709:ispace=bt709"
        
        elif mode == ColorSpaceMode.SIMULATION:
            filters = []
            if saturation != 0:
                sat_val = 1.0 + saturation
                filters.append(f"saturation={sat_val}")
            if contrast != 0:
                con_val = 1.0 + contrast
                filters.append(f"contrast={con_val}")
            if gamma != 0:
                gamma_val = 1.0 + gamma
                filters.append(f"gamma={gamma_val}")
            if filters:
                return f"eq={':'.join(filters)}"
            return None
        
        return None
    
    def _get_output_format(self, output_file: str) -> str:
        ext = os.path.splitext(output_file)[1].lower()
        if ext == ".flv":
            return "flv"
        return "mp4"
    
    def build_single_pass_command(
        self,
        input_file: str,
        output_file: str,
        config: EncodingConfig,
        extra_filters: Optional[List[str]] = None
    ) -> List[str]:
        cmd = [self.ffmpeg_path, "-y", "-i", input_file]
        
        output_format = self._get_output_format(output_file)
        
        if config.video.enabled:
            cmd.extend(self.build_video_encoding_params(config.video, output_format))
        else:
            cmd.extend(["-vn"])
        
        if config.audio.enabled:
            cmd.extend(self.build_audio_encoding_params(config.audio, output_format))
        else:
            cmd.extend(["-an"])
        
        cmd.append(output_file)
        return cmd
    
    def build_two_pass_commands(
        self,
        input_file: str,
        output_file: str,
        config: EncodingConfig,
        extra_filters: Optional[List[str]] = None
    ) -> tuple:
        output_format = self._get_output_format(output_file)
        base_cmd = [self.ffmpeg_path, "-y", "-i", input_file]
        
        pass1_cmd = base_cmd.copy()
        pass1_cmd.extend(self.build_video_encoding_params(config.video, output_format))
        pass1_cmd.extend([
            "-pass", "1",
            "-f", output_format,
            os.devnull if os.name == "nt" else "/dev/null",
        ])
        
        pass2_cmd = base_cmd.copy()
        pass2_cmd.extend(self.build_video_encoding_params(config.video, output_format))
        pass2_cmd.extend([
            "-pass", "2",
        ])
        
        if config.audio.enabled:
            pass2_cmd.extend(self.build_audio_encoding_params(config.audio, output_format))
        else:
            pass2_cmd.extend(["-an"])
        
        pass2_cmd.append(output_file)
        
        return pass1_cmd, pass2_cmd
    
    def build_decode_command(self, input_file: str, output_file: str) -> List[str]:
        return [
            self.ffmpeg_path, "-y", "-i", input_file,
            "-vcodec", "rawvideo",
            "-pix_fmt", "yuv420p",
            "-an",
            output_file
        ]
    
    def build_reencode_command(
        self,
        input_file: str,
        output_file: str,
        config: EncodingConfig,
        color_error_filter: Optional[str] = None
    ) -> List[str]:
        output_format = self._get_output_format(output_file)
        cmd = [self.ffmpeg_path, "-y", "-i", input_file]
        
        if color_error_filter:
            cmd.extend([self._get_filter_option(), color_error_filter])
        
        cmd.extend(self.build_video_encoding_params(config.video, output_format))
        
        if config.audio.enabled:
            cmd.extend(self.build_audio_encoding_params(config.audio, output_format))
        else:
            cmd.extend(["-an"])
        
        cmd.append(output_file)
        return cmd
