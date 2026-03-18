"""
编码管线实现
预处理、编码、音频与封装统一走现代 FFmpeg，
并使用 x264 参数模拟 2010 年代常见编码风格。
"""
import os
import subprocess
import re
import tempfile
import shutil
import copy
from typing import Optional, Callable
from pathlib import Path

from ..ffmpeg_paths import get_bundled_ffmpeg_paths, resolve_ffmpeg_path

from ..config.types import (
    EncodingConfig,
    EncodeMode,
    ColorSpaceMode,
    AudioCodec,
    ContainerFormat,
    ResolutionPreset,
    TransportProtocol,
)
from .command_builder import FFmpegCommandBuilder
from .colorspace import process_color_space


class EncodingPipeline:
    def __init__(
        self,
        ffmpeg_path: Optional[str] = None,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        error_callback: Optional[Callable[[str], None]] = None
    ):
        self.ffmpeg_path = resolve_ffmpeg_path(ffmpeg_path)
        self.progress_callback = progress_callback
        self.error_callback = error_callback
        self._process = None
        self._cancelled = False
        
        self._modern_ffmpeg, self._legacy_ffmpeg = get_bundled_ffmpeg_paths()
        self._system_ffmpeg = self._modern_ffmpeg or self._legacy_ffmpeg
        self._video_ffmpeg = self.ffmpeg_path
        self.builder = FFmpegCommandBuilder(self._video_ffmpeg, legacy_mode=False)
        self._system_builder = FFmpegCommandBuilder(self._system_ffmpeg, legacy_mode=False) if self._system_ffmpeg else None
    
    def _get_system_ffmpeg_path(self) -> Optional[str]:
        modern_path, legacy_path = get_bundled_ffmpeg_paths()
        return modern_path or legacy_path
    
    def _parse_progress(self, line: str, duration: float = None) -> Optional[float]:
        time_match = re.search(r"time=(\d+):(\d+):(\d+\.?\d*)", line)
        if time_match:
            hours = float(time_match.group(1))
            minutes = float(time_match.group(2))
            seconds = float(time_match.group(3))
            current_time = hours * 3600 + minutes * 60 + seconds
            if duration and duration > 0:
                return min(current_time / duration, 1.0)
        return None
    
    def _run_ffmpeg(self, cmd: list, step_name: str = "Encoding", legacy_mode: bool = False) -> bool:
        try:
            if not legacy_mode and "-nostdin" not in cmd:
                cmd = [cmd[0], "-nostdin"] + cmd[1:]
            print(f"\n[CMD] {' '.join(cmd)}\n")
            
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            
            duration = None
            full_output = []
            
            while True:
                if self._cancelled:
                    self._process.terminate()
                    return False
                
                line = self._process.stdout.readline()
                if not line:
                    if self._process.poll() is not None:
                        break
                    continue
                
                full_output.append(line)
                print(line, end='')
                
                if "Duration:" in line:
                    dur_match = re.search(r"Duration: (\d+):(\d+):(\d+\.?\d*)", line)
                    if dur_match:
                        hours = float(dur_match.group(1))
                        minutes = float(dur_match.group(2))
                        seconds = float(dur_match.group(3))
                        duration = hours * 3600 + minutes * 60 + seconds
                
                if "time=" in line:
                    progress = self._parse_progress(line, duration)
                    if progress is not None and self.progress_callback:
                        self.progress_callback(step_name, progress)
            
            return_code = self._process.returncode
            
            if return_code != 0 and return_code != 3221225477:
                if self.error_callback:
                    self.error_callback(''.join(full_output))
                return False
            
            return True
            
        except Exception as e:
            print(f"\n[EXCEPTION] {e}")
            if self.error_callback:
                self.error_callback(str(e))
            return False
    
    def _preprocess_video(
        self,
        input_file: str,
        output_avi: str,
        config: EncodingConfig
    ) -> bool:
        if not self._system_ffmpeg:
            print("System FFmpeg not found, cannot preprocess video")
            return False
        
        preprocess_filters = self._system_builder.build_preprocess_filters(config.effects.preprocess)
        
        cmd = [
            self._system_ffmpeg, "-y", "-i", input_file,
        ]
        
        if preprocess_filters:
            cmd.extend(["-vf", ",".join(preprocess_filters)])
        
        cmd.extend([
            "-vcodec", "mpeg4", "-q:v", "2",
            "-acodec", "pcm_s16le",
            output_avi
        ])
        
        print(f"\n[Preprocessing with modern FFmpeg (filter support)]")
        return self._run_ffmpeg(cmd, "Preprocessing")
    
    def _encode_video_only(
        self,
        input_file: str,
        output_file: str,
        config: EncodingConfig
    ) -> bool:
        output_format = "flv" if output_file.lower().endswith(".flv") else "mp4"
        video_params = self.builder.build_video_encoding_params(config.video, output_format)

        if config.video.encode_mode == EncodeMode.TWO_PASS_VBR:
            passlog = os.path.join(tempfile.gettempdir(), f"syrmetroize_{os.path.basename(output_file)}")
            null_out = "NUL" if os.name == "nt" else "/dev/null"

            pass1_cmd = [self.builder.ffmpeg_path, "-y", "-i", input_file]
            pass1_cmd.extend(video_params)
            pass1_cmd.extend([
                "-pass", "1",
                "-passlogfile", passlog,
                "-an",
                "-f", output_format,
                null_out,
            ])

            if not self._run_ffmpeg(pass1_cmd, "Video Pass 1"):
                return False

            if self._cancelled:
                return False

            pass2_cmd = [self.builder.ffmpeg_path, "-y", "-i", input_file]
            pass2_cmd.extend(video_params)
            pass2_cmd.extend([
                "-pass", "2",
                "-passlogfile", passlog,
                "-an",
                output_file,
            ])

            ok = self._run_ffmpeg(pass2_cmd, "Video Pass 2")

            for suffix in ["-0.log", "-0.log.mbtree", ".log", ".log.mbtree"]:
                log_file = f"{passlog}{suffix}"
                if os.path.exists(log_file):
                    try:
                        os.remove(log_file)
                    except Exception:
                        pass

            return ok

        cmd = [self.builder.ffmpeg_path, "-y", "-i", input_file]
        cmd.extend(video_params)
        cmd.extend(["-an", output_file])
        print(f"\n[Encoding video with x264 (2010 style)]")
        return self._run_ffmpeg(cmd, "Video Encoding")
    
    def _process_audio(
        self,
        input_file: str,
        output_audio: str,
        config: EncodingConfig
    ) -> bool:
        if not self._system_ffmpeg and not self.builder.ffmpeg_path:
            print("FFmpeg not found, cannot process audio")
            return False
        
        if not config.audio.enabled:
            return True
        
        audio_builder = self._system_builder or self.builder
        audio_filters = audio_builder.build_audio_filters(config.audio)
        audio_ffmpeg = self._system_ffmpeg or self.builder.ffmpeg_path
        
        cmd = [
            audio_ffmpeg, "-y", "-i", input_file,
        ]
        
        if audio_filters:
            cmd.extend(["-af", ",".join(audio_filters)])
        
        if config.audio.codec == AudioCodec.HE_AAC_V1:
            cmd.extend(["-c:a", "aac", "-profile:a", "aac_he"])
        else:
            cmd.extend(["-c:a", "aac", "-profile:a", "aac_low"])

        cmd.extend(["-b:a", f"{config.audio.bitrate}k"])
        
        cmd.extend([
            "-ar", str(config.audio.sample_rate),
            "-ac", "2",
            "-vn",
            output_audio
        ])
        
        print(f"\n[Processing audio with modern FFmpeg (filters support)]")
        return self._run_ffmpeg(cmd, "Audio Processing")
    
    def _merge_video_audio(
        self,
        video_file: str,
        audio_file: str,
        output_file: str
    ) -> bool:
        if not self._system_ffmpeg:
            print("System FFmpeg not found, cannot merge")
            if video_file != output_file:
                shutil.copy(video_file, output_file)
            return True
        
        cmd = [
            self._system_ffmpeg, "-y",
            "-i", video_file,
            "-i", audio_file,
            "-c:v", "copy",
            "-c:a", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-shortest",
            output_file
        ]
        
        print(f"\n[Merging video and audio]")
        return self._run_ffmpeg(cmd, "Merging")

    def _remux_to_target_container(
        self,
        input_file: str,
        output_file: str,
        config: EncodingConfig
    ) -> bool:
        ffmpeg_bin = self._system_ffmpeg or self.builder.ffmpeg_path
        if not ffmpeg_bin:
            if input_file != output_file:
                shutil.copy(input_file, output_file)
            return True

        target_format = "flv" if config.container == ContainerFormat.FLV else "mp4"

        cmd = [
            ffmpeg_bin, "-y",
            "-i", input_file,
            "-c:v", "copy",
            "-c:a", "copy",
            "-f", target_format,
            output_file,
        ]

        print(f"\n[Final container remux: {target_format}]")
        return self._run_ffmpeg(cmd, "Final Mux")

    def _apply_transport_packaging(self, output_file: str, config: EncodingConfig) -> bool:
        transport = config.transport
        ffmpeg_bin = self._system_ffmpeg or self.builder.ffmpeg_path

        if transport == TransportProtocol.HLS:
            if not ffmpeg_bin:
                print("FFmpeg not found, cannot generate HLS packaging")
                return False

            playlist_path = self._resolve_hls_playlist_path(output_file, config.hls_playlist_path)
            hls_dir = os.path.dirname(playlist_path)
            if hls_dir:
                os.makedirs(hls_dir, exist_ok=True)
            segment_path = os.path.join(hls_dir, "segment_%03d.ts")

            cmd = [
                ffmpeg_bin, "-y",
                "-i", output_file,
                "-c", "copy",
                "-hls_time", "10",
                "-hls_list_size", "0",
                "-hls_segment_filename", segment_path,
                "-f", "hls",
                playlist_path,
            ]

            print("\n[Transport packaging: HLS]")
            if not self._run_ffmpeg(cmd, "HLS Packaging"):
                return False

            self._write_transport_sidecar(output_file, config, playlist_path=playlist_path)
            return True

        self._write_transport_sidecar(output_file, config)
        return True

    def _resolve_hls_playlist_path(self, output_file: str, configured_path: Optional[str]) -> str:
        if not configured_path:
            output_path = Path(output_file)
            hls_dir = output_path.with_suffix("").as_posix() + "_hls"
            return os.path.join(hls_dir, "index.m3u8")

        expanded = os.path.expanduser(configured_path)
        playlist_candidate = Path(expanded)
        if not playlist_candidate.is_absolute():
            playlist_candidate = Path(output_file).resolve().parent / playlist_candidate

        if playlist_candidate.suffix.lower() == ".m3u8":
            return str(playlist_candidate)

        return str(playlist_candidate / "index.m3u8")

    def _write_transport_sidecar(
        self,
        output_file: str,
        config: EncodingConfig,
        playlist_path: Optional[str] = None
    ) -> None:
        sidecar = output_file + ".transport.txt"
        lines = []
        lines.append(f"transport={config.transport.value}")
        lines.append(f"container={config.container.value}")
        lines.append(f"output={output_file}")

        if config.transport == TransportProtocol.RTMP:
            lines.append("suggested_publish_command=")
            lines.append(
                f"ffmpeg -re -stream_loop -1 -i \"{output_file}\" -c copy -f flv {config.rtmp_publish_url}"
            )
        elif config.transport == TransportProtocol.HLS:
            lines.append(f"hls_playlist={playlist_path or ''}")
            lines.append("notes=Use a static HTTP server to host the generated m3u8 and ts files")
        else:
            lines.append("notes=Use HTTP progressive download directly with the output file")

        try:
            with open(sidecar, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            print(f"Warning: failed to write transport sidecar: {e}")
    
    def _apply_color_space_effect(
        self,
        input_file: str,
        output_file: str,
        config: EncodingConfig
    ) -> bool:
        mode = config.effects.color_space.mode

        if mode == ColorSpaceMode.NONE and self._should_auto_apply_flash_simulation(config):
            mode = ColorSpaceMode.SIMULATION
            print("\n[Auto color space simulation enabled for legacy path]")

        if mode == ColorSpaceMode.NONE:
            if input_file != output_file:
                shutil.copy(input_file, output_file)
            return True
        
        if mode == ColorSpaceMode.ERROR_MAPPING:
            process_mode = "error_mapping"
        else:
            process_mode = "simulation"
        
        print(f"\n[Applying color space effect (Flash player error)]")
        print(f"  Mode: {process_mode}")
        if process_mode == "simulation":
            print(f"  Saturation: {config.effects.color_space.saturation_adjust}")
            print(f"  Contrast: {config.effects.color_space.contrast_adjust}")
            print(f"  Gamma: {config.effects.color_space.gamma_adjust}")
        else:
            print("  Saturation/Contrast/Gamma: ignored in error_mapping mode")
        print("  Backend: FFmpeg only")
        
        def color_progress(p):
            if self.progress_callback:
                self.progress_callback("Color Space", p)
        
        return process_color_space(
            input_file,
            output_file,
            mode=process_mode,
            saturation=config.effects.color_space.saturation_adjust,
            contrast=config.effects.color_space.contrast_adjust,
            gamma=config.effects.color_space.gamma_adjust,
            progress_callback=color_progress,
            ffmpeg_path=self._system_ffmpeg or self.builder.ffmpeg_path,
        )

    def _should_auto_apply_flash_simulation(self, config: EncodingConfig) -> bool:
        color_cfg = config.effects.color_space
        if not color_cfg.auto_apply_legacy_flash_simulation:
            return False

        # Legacy path heuristic: FLV + SD resolution is where player-side matrix issues were most common.
        is_legacy_container = config.container == ContainerFormat.FLV
        is_sd_resolution = config.video.resolution in {
            ResolutionPreset.P240,
            ResolutionPreset.P360,
            ResolutionPreset.P480,
        }
        return is_legacy_container and is_sd_resolution
    
    def cancel(self):
        self._cancelled = True
        if self._process:
            self._process.terminate()
    
    def encode_single(
        self,
        input_file: str,
        output_file: str,
        config: EncodingConfig
    ) -> bool:
        temp_dir = tempfile.gettempdir()
        intermediate_avi = os.path.join(temp_dir, "syrmetroize_intermediate.avi")
        encoded_video = os.path.join(temp_dir, "syrmetroize_encoded.mp4")
        processed_audio = os.path.join(temp_dir, "syrmetroize_audio.m4a")
        merged_output = os.path.join(temp_dir, "syrmetroize_merged.mp4")
        post_color_output = os.path.join(temp_dir, "syrmetroize_post_color.mp4")
        
        try:
            if not self._preprocess_video(input_file, intermediate_avi, config):
                return False
            
            if self._cancelled:
                return False
            
            if not self._encode_video_only(intermediate_avi, encoded_video, config):
                return False
            
            if self._cancelled:
                return False
            
            if not self._process_audio(input_file, processed_audio, config):
                return False
            
            if self._cancelled:
                return False
            
            if not self._merge_video_audio(encoded_video, processed_audio, merged_output):
                return False
            
            if self._cancelled:
                return False
            
            if not self._apply_color_space_effect(merged_output, post_color_output, config):
                return False

            if self._cancelled:
                return False

            if not self._remux_to_target_container(post_color_output, output_file, config):
                return False

            if self._cancelled:
                return False

            if not self._apply_transport_packaging(output_file, config):
                return False
            
            return True
            
        finally:
            for temp_file in [intermediate_avi, encoded_video, processed_audio, merged_output, post_color_output]:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
    
    def encode_double(
        self,
        input_file: str,
        output_file: str,
        config: EncodingConfig
    ) -> bool:
        temp_dir = tempfile.gettempdir()
        intermediate_avi = os.path.join(temp_dir, "syrmetroize_intermediate.avi")
        first_pass_video = os.path.join(temp_dir, "syrmetroize_first_pass.mp4")
        second_pass_video = os.path.join(temp_dir, "syrmetroize_second_pass.mp4")
        processed_audio = os.path.join(temp_dir, "syrmetroize_audio.m4a")
        merged_output = os.path.join(temp_dir, "syrmetroize_merged.mp4")
        post_color_output = os.path.join(temp_dir, "syrmetroize_post_color.mp4")
        
        try:
            if not self._preprocess_video(input_file, intermediate_avi, config):
                return False
            
            if self._cancelled:
                return False
            
            first_config = copy.deepcopy(config)
            first_config.video.resolution = config.effects.double_encode.first_pass_resolution

            if not self._encode_video_only(intermediate_avi, first_pass_video, first_config):
                return False
            
            if self._cancelled:
                return False
            
            if not self._encode_video_only(first_pass_video, second_pass_video, config):
                return False
            
            if self._cancelled:
                return False
            
            if not self._process_audio(input_file, processed_audio, config):
                return False
            
            if self._cancelled:
                return False
            
            if not self._merge_video_audio(second_pass_video, processed_audio, merged_output):
                return False
            
            if self._cancelled:
                return False
            
            if not self._apply_color_space_effect(merged_output, post_color_output, config):
                return False

            if self._cancelled:
                return False

            if not self._remux_to_target_container(post_color_output, output_file, config):
                return False

            if self._cancelled:
                return False

            if not self._apply_transport_packaging(output_file, config):
                return False
            
            return True
            
        finally:
            for temp_file in [intermediate_avi, first_pass_video, second_pass_video, processed_audio, merged_output, post_color_output]:
                if os.path.exists(temp_file):
                    try:
                        os.remove(temp_file)
                    except:
                        pass
    
    def encode(
        self,
        input_file: str,
        output_file: str,
        config: EncodingConfig
    ) -> bool:
        self._cancelled = False
        
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        if config.effects.double_encode.enabled:
            return self.encode_double(input_file, output_file, config)
        else:
            return self.encode_single(input_file, output_file, config)
