"""
GUI界面实现 - 使用 tkinter
"""
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional, Callable
import threading

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

from ..config.types import (
    EncodingConfig, VideoConfig, AudioConfig, EffectsConfig,
    PreprocessConfig, DoubleEncodeConfig, ColorSpaceConfig,
    VideoProfile, ResolutionPreset, AudioCodec, EncodeMode,
    ContainerFormat, DeinterlaceMethod, ColorSpaceMode, TransportProtocol
)
from ..config.presets import get_preset, get_all_presets
from ..encoder.pipeline import EncodingPipeline


class CollapsibleFrame(ttk.Frame):
    def __init__(self, parent, title: str, **kwargs):
        super().__init__(parent, **kwargs)
        
        self.is_expanded = tk.BooleanVar(value=True)
        
        self.header = ttk.Frame(self)
        self.header.pack(fill="x")
        
        self.toggle_btn = ttk.Checkbutton(
            self.header,
            text=title,
            variable=self.is_expanded,
            command=self._toggle
        )
        self.toggle_btn.pack(side="left")
        
        self.content = ttk.Frame(self)
        self.content.pack(fill="both", expand=True, padx=20)
    
    def _toggle(self):
        if self.is_expanded.get():
            self.content.pack(fill="both", expand=True, padx=20)
        else:
            self.content.pack_forget()


class MainWindow:
    def __init__(self, ffmpeg_path: str):
        self.ffmpeg_path = ffmpeg_path
        self.pipeline: Optional[EncodingPipeline] = None
        self.is_encoding = False
        self._drag_drop_available = TkinterDnD is not None
        
        self.root = TkinterDnD.Tk() if self._drag_drop_available else tk.Tk()
        self.root.title("SyrMetroize")
        self.root.geometry("800x900")
        self.root.minsize(600, 700)
        
        self.config = EncodingConfig()
        
        self._create_widgets()
        self._layout_widgets()
        self._setup_drag_drop()
        self._update_transport_field_states()
        self._refresh_pipeline_preview()
    
    def _create_widgets(self):
        self.file_frame = ttk.LabelFrame(self.root, text="文件选择")
        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        
        ttk.Label(self.file_frame, text="输入文件:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.input_entry = ttk.Entry(self.file_frame, textvariable=self.input_var, width=50)
        self.input_entry.grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(self.file_frame, text="浏览...", command=self._browse_input).grid(row=0, column=2, padx=5, pady=5)
        
        ttk.Label(self.file_frame, text="输出文件:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.output_entry = ttk.Entry(self.file_frame, textvariable=self.output_var, width=50)
        self.output_entry.grid(row=1, column=1, padx=5, pady=5)
        ttk.Button(self.file_frame, text="浏览...", command=self._browse_output).grid(row=1, column=2, padx=5, pady=5)
        
        self.preset_frame = ttk.LabelFrame(self.root, text="预设选择")
        self.preset_var = tk.StringVar(value="custom")
        
        presets = get_all_presets()
        preset_options = [("自定义", "custom")]
        for key, preset in presets.items():
            preset_options.append((preset.name, key))
        
        for i, (label, value) in enumerate(preset_options):
            ttk.Radiobutton(
                self.preset_frame,
                text=label,
                value=value,
                variable=self.preset_var,
                command=self._on_preset_change
            ).grid(row=0, column=i, padx=10, pady=5)

        self.preview_frame = ttk.LabelFrame(self.root, text="处理流程预览（无需了解 pipeline）")
        self.preview_text = tk.Text(self.preview_frame, height=8, wrap="word")
        self.preview_text.pack(fill="x", padx=8, pady=6)
        self.preview_text.configure(state="disabled")
        
        self._create_module_panels()
        
        self.progress_frame = ttk.LabelFrame(self.root, text="处理进度")
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(
            self.progress_frame,
            variable=self.progress_var,
            maximum=100
        )
        self.progress_bar.pack(fill="x", padx=10, pady=5)
        
        self.status_var = tk.StringVar(value="就绪")
        self.status_label = ttk.Label(self.progress_frame, textvariable=self.status_var)
        self.status_label.pack(pady=5)
        
        self.control_frame = ttk.Frame(self.root)
        self.cancel_btn = ttk.Button(
            self.control_frame,
            text="取消",
            command=self._cancel_encoding,
            state="disabled"
        )
        self.cancel_btn.pack(side="right", padx=10)

        self.start_btn = ttk.Button(
            self.control_frame,
            text="开始处理",
            command=self._start_encoding
        )
        self.start_btn.pack(side="right", padx=10)
    
    def _create_module_panels(self):
        notebook = ttk.Notebook(self.root)
        self.notebook = notebook
        
        self.video_frame = ttk.Frame(notebook)
        self._create_video_panel(self.video_frame)
        notebook.add(self.video_frame, text="视频编码")
        
        self.audio_frame = ttk.Frame(notebook)
        self._create_audio_panel(self.audio_frame)
        notebook.add(self.audio_frame, text="音频编码")
        
        self.effects_frame = ttk.Frame(notebook)
        self._create_effects_panel(self.effects_frame)
        notebook.add(self.effects_frame, text="效果处理")
        
        self.preprocess_frame = ttk.Frame(notebook)
        self._create_preprocess_panel(self.preprocess_frame)
        notebook.add(self.preprocess_frame, text="预处理")
    
    def _create_video_panel(self, parent):
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        row = 0
        
        ttk.Label(frame, text="H.264 Profile:").grid(row=row, column=0, sticky="w", pady=2)
        self.video_profile_var = tk.StringVar(value="main")
        profile_combo = ttk.Combobox(
            frame,
            textvariable=self.video_profile_var,
            values=["baseline", "main", "high"],
            state="readonly",
            width=15
        )
        profile_combo.grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="分辨率:").grid(row=row, column=0, sticky="w", pady=2)
        self.video_resolution_var = tk.StringVar(value="360p")
        resolution_combo = ttk.Combobox(
            frame,
            textvariable=self.video_resolution_var,
            values=["240p", "360p", "480p", "720p"],
            state="readonly",
            width=15
        )
        resolution_combo.grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="编码模式:").grid(row=row, column=0, sticky="w", pady=2)
        self.video_encode_mode_var = tk.StringVar(value="1pass")
        mode_combo = ttk.Combobox(
            frame,
            textvariable=self.video_encode_mode_var,
            values=["1pass", "2pass"],
            state="readonly",
            width=15
        )
        mode_combo.grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="平均码率 (kbps):").grid(row=row, column=0, sticky="w", pady=2)
        self.video_bitrate_var = tk.IntVar(value=600)
        ttk.Spinbox(frame, from_=100, to=5000, textvariable=self.video_bitrate_var, width=10).grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="峰值码率 (kbps):").grid(row=row, column=0, sticky="w", pady=2)
        self.video_max_bitrate_var = tk.IntVar(value=900)
        ttk.Spinbox(frame, from_=100, to=10000, textvariable=self.video_max_bitrate_var, width=10).grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="关键帧间隔 (keyint):").grid(row=row, column=0, sticky="w", pady=2)
        self.video_keyint_var = tk.IntVar(value=100)
        ttk.Spinbox(frame, from_=1, to=300, textvariable=self.video_keyint_var, width=10).grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="B帧数量:").grid(row=row, column=0, sticky="w", pady=2)
        self.video_bframes_var = tk.IntVar(value=2)
        ttk.Spinbox(frame, from_=0, to=4, textvariable=self.video_bframes_var, width=10).grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="参考帧数量:").grid(row=row, column=0, sticky="w", pady=2)
        self.video_ref_var = tk.IntVar(value=3)
        ttk.Spinbox(frame, from_=1, to=5, textvariable=self.video_ref_var, width=10).grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="封装格式:").grid(row=row, column=0, sticky="w", pady=2)
        self.container_var = tk.StringVar(value="mp4")
        container_combo = ttk.Combobox(
            frame,
            textvariable=self.container_var,
            values=["flv", "mp4"],
            state="readonly",
            width=15
        )
        container_combo.grid(row=row, column=1, sticky="w", pady=2)
        self.container_var.trace_add("write", self._on_container_change)
        row += 1

        ttk.Label(frame, text="传输协议:").grid(row=row, column=0, sticky="w", pady=2)
        self.transport_var = tk.StringVar(value="http")
        transport_combo = ttk.Combobox(
            frame,
            textvariable=self.transport_var,
            values=["rtmp", "hls", "http"],
            state="readonly",
            width=15
        )
        transport_combo.grid(row=row, column=1, sticky="w", pady=2)
        self.transport_var.trace_add("write", self._on_transport_change)
        row += 1

        ttk.Label(frame, text="RTMP 推流地址:").grid(row=row, column=0, sticky="w", pady=2)
        self.rtmp_url_var = tk.StringVar(value="rtmp://localhost/live/syrmetroize")
        self.rtmp_url_entry = ttk.Entry(frame, textvariable=self.rtmp_url_var, width=40)
        self.rtmp_url_entry.grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        ttk.Label(frame, text="HLS 输出路径:").grid(row=row, column=0, sticky="w", pady=2)
        self.hls_output_var = tk.StringVar()
        self.hls_output_entry = ttk.Entry(frame, textvariable=self.hls_output_var, width=40)
        self.hls_output_entry.grid(row=row, column=1, sticky="w", pady=2)
        self.hls_output_browse_btn = ttk.Button(frame, text="浏览...", command=self._browse_hls_output)
        self.hls_output_browse_btn.grid(row=row, column=2, padx=5, pady=2)
    
    def _create_audio_panel(self, parent):
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        row = 0
        
        self.audio_enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="启用音频编码", variable=self.audio_enabled_var).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="音频编码:").grid(row=row, column=0, sticky="w", pady=2)
        self.audio_codec_var = tk.StringVar(value="aac-lc")
        codec_combo = ttk.Combobox(
            frame,
            textvariable=self.audio_codec_var,
            values=["he-aac", "aac-lc"],
            state="readonly",
            width=15
        )
        codec_combo.grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="音频码率 (kbps):").grid(row=row, column=0, sticky="w", pady=2)
        self.audio_bitrate_var = tk.IntVar(value=96)
        ttk.Spinbox(frame, from_=32, to=320, textvariable=self.audio_bitrate_var, width=10).grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="采样率 (Hz):").grid(row=row, column=0, sticky="w", pady=2)
        self.audio_sample_rate_var = tk.IntVar(value=44100)
        ttk.Combobox(
            frame,
            textvariable=self.audio_sample_rate_var,
            values=[22050, 32000, 44100, 48000],
            state="readonly",
            width=15
        ).grid(row=row, column=1, sticky="w", pady=2)
        row += 1
        
        self.audio_ms_stereo_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text="MS立体声编码", variable=self.audio_ms_stereo_var).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
        row += 1
        
        ttk.Label(frame, text="响度目标 (LUFS):").grid(row=row, column=0, sticky="w", pady=2)
        self.audio_lufs_var = tk.DoubleVar(value=-16.0)
        ttk.Spinbox(frame, from_=-24, to=-6, textvariable=self.audio_lufs_var, width=10).grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        ttk.Label(frame, text="Side声道降低 (dB):").grid(row=row, column=0, sticky="w", pady=2)
        self.audio_side_reduce_var = tk.DoubleVar(value=0.0)
        ttk.Spinbox(frame, from_=0, to=6, increment=0.5, textvariable=self.audio_side_reduce_var, width=10).grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        ttk.Label(frame, text="动态压缩比:").grid(row=row, column=0, sticky="w", pady=2)
        self.audio_compression_ratio_var = tk.DoubleVar(value=1.0)
        ttk.Spinbox(frame, from_=1.0, to=6.0, increment=0.5, textvariable=self.audio_compression_ratio_var, width=10).grid(row=row, column=1, sticky="w", pady=2)
        row += 1

        self.audio_high_pass_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="高通滤波 (80Hz)", variable=self.audio_high_pass_var).grid(row=row, column=0, columnspan=2, sticky="w", pady=2)
    
    def _create_effects_panel(self, parent):
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        row = 0
        
        double_encode_frame = ttk.LabelFrame(frame, text="双编码")
        double_encode_frame.grid(row=row, column=0, sticky="ew", pady=5)
        
        self.double_encode_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(double_encode_frame, text="启用双编码", variable=self.double_encode_var).pack(anchor="w", padx=5, pady=2)
        
        ttk.Label(double_encode_frame, text="第一次编码分辨率:").pack(anchor="w", padx=5)
        self.double_encode_res_var = tk.StringVar(value="360p")
        ttk.Combobox(
            double_encode_frame,
            textvariable=self.double_encode_res_var,
            values=["240p", "360p", "480p"],
            state="readonly",
            width=10
        ).pack(anchor="w", padx=5, pady=2)
        
        row += 1
        
        color_space_frame = ttk.LabelFrame(frame, text="色彩空间处理")
        color_space_frame.grid(row=row, column=0, sticky="ew", pady=5)
        
        ttk.Label(color_space_frame, text="处理模式:").pack(anchor="w", padx=5, pady=2)
        self.color_space_mode_var = tk.StringVar(value="none")
        self.color_space_mode_var.trace_add("write", self._on_mode_related_change)
        
        mode_frame = ttk.Frame(color_space_frame)
        mode_frame.pack(fill="x", padx=5)
        
        ttk.Radiobutton(
            mode_frame, text="无", value="none", variable=self.color_space_mode_var
        ).pack(side="left", padx=5)
        ttk.Radiobutton(
            mode_frame, text="错误映射", value="error_mapping", variable=self.color_space_mode_var
        ).pack(side="left", padx=5)
        ttk.Radiobutton(
            mode_frame, text="模拟", value="simulation", variable=self.color_space_mode_var
        ).pack(side="left", padx=5)

        self.color_space_auto_legacy_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            color_space_frame,
            text="自动在 FLV + 480P及以下启用模拟",
            variable=self.color_space_auto_legacy_var,
        ).pack(anchor="w", padx=5, pady=2)
        
        sim_frame = ttk.Frame(color_space_frame)
        sim_frame.pack(fill="x", padx=5, pady=5)
        
        self.color_param_hint_var = tk.StringVar(value="以下参数仅在“模拟”模式生效")
        self.color_param_hint_label = ttk.Label(sim_frame, textvariable=self.color_param_hint_var)
        self.color_param_hint_label.pack(anchor="w")

        ttk.Label(sim_frame, text="饱和度调整 (-0.1 ~ 0.1):").pack(anchor="w")
        self.color_space_saturation_var = tk.DoubleVar(value=-0.08)
        self.color_space_saturation_scale = ttk.Scale(
            sim_frame,
            from_=-0.15,
            to=0.05,
            variable=self.color_space_saturation_var,
            orient="horizontal"
        )
        self.color_space_saturation_scale.pack(fill="x")
        
        ttk.Label(sim_frame, text="对比度调整 (-0.1 ~ 0.2):").pack(anchor="w")
        self.color_space_contrast_var = tk.DoubleVar(value=0.03)
        self.color_space_contrast_scale = ttk.Scale(
            sim_frame,
            from_=-0.1,
            to=0.2,
            variable=self.color_space_contrast_var,
            orient="horizontal"
        )
        self.color_space_contrast_scale.pack(fill="x")
        
        ttk.Label(sim_frame, text="Gamma调整 (-0.1 ~ 0.1):").pack(anchor="w")
        self.color_space_gamma_var = tk.DoubleVar(value=0.02)
        self.color_space_gamma_scale = ttk.Scale(
            sim_frame,
            from_=-0.1,
            to=0.1,
            variable=self.color_space_gamma_var,
            orient="horizontal"
        )
        self.color_space_gamma_scale.pack(fill="x")
    
    def _create_preprocess_panel(self, parent):
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)
        
        row = 0
        
        denoise_frame = ttk.LabelFrame(frame, text="降噪")
        denoise_frame.grid(row=row, column=0, sticky="ew", pady=5)
        
        self.denoise_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(denoise_frame, text="启用降噪", variable=self.denoise_var).pack(anchor="w", padx=5, pady=2)
        
        ttk.Label(denoise_frame, text="降噪强度:").pack(anchor="w", padx=5)
        self.denoise_strength_var = tk.DoubleVar(value=4.0)
        ttk.Scale(denoise_frame, from_=1, to=10, variable=self.denoise_strength_var, orient="horizontal").pack(fill="x", padx=5)
        
        row += 1
        
        deint_frame = ttk.LabelFrame(frame, text="去隔行")
        deint_frame.grid(row=row, column=0, sticky="ew", pady=5)
        
        self.deinterlace_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(deint_frame, text="启用去隔行", variable=self.deinterlace_var).pack(anchor="w", padx=5, pady=2)
        
        ttk.Label(deint_frame, text="去隔行方法:").pack(anchor="w", padx=5)
        self.deinterlace_method_var = tk.StringVar(value="yadif")
        ttk.Combobox(
            deint_frame,
            textvariable=self.deinterlace_method_var,
            values=["yadif", "yadif=1", "discard"],
            state="readonly",
            width=10
        ).pack(anchor="w", padx=5, pady=2)
        
        row += 1
        
        sharpen_frame = ttk.LabelFrame(frame, text="锐化")
        sharpen_frame.grid(row=row, column=0, sticky="ew", pady=5)
        
        self.sharpen_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sharpen_frame, text="启用锐化", variable=self.sharpen_var).pack(anchor="w", padx=5, pady=2)
        
        ttk.Label(sharpen_frame, text="锐化强度:").pack(anchor="w", padx=5)
        self.sharpen_strength_var = tk.DoubleVar(value=1.0)
        ttk.Scale(sharpen_frame, from_=0.5, to=3, variable=self.sharpen_strength_var, orient="horizontal").pack(fill="x", padx=5)
        
        row += 1
        
        cs_frame = ttk.LabelFrame(frame, text="对比度/饱和度")
        cs_frame.grid(row=row, column=0, sticky="ew", pady=5)
        
        self.contrast_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cs_frame, text="启用对比度调整", variable=self.contrast_var).pack(anchor="w", padx=5, pady=2)
        
        ttk.Label(cs_frame, text="对比度:").pack(anchor="w", padx=5)
        self.contrast_value_var = tk.DoubleVar(value=1.0)
        ttk.Scale(cs_frame, from_=0.5, to=2, variable=self.contrast_value_var, orient="horizontal").pack(fill="x", padx=5)
        
        self.saturation_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(cs_frame, text="启用饱和度调整", variable=self.saturation_var).pack(anchor="w", padx=5, pady=2)
        
        ttk.Label(cs_frame, text="饱和度:").pack(anchor="w", padx=5)
        self.saturation_value_var = tk.DoubleVar(value=1.0)
        ttk.Scale(cs_frame, from_=0.5, to=2, variable=self.saturation_value_var, orient="horizontal").pack(fill="x", padx=5)
    
    def _layout_widgets(self):
        self.file_frame.pack(fill="x", padx=10, pady=5)
        self.preset_frame.pack(fill="x", padx=10, pady=5)
        self.preview_frame.pack(fill="x", padx=10, pady=5)
        self.control_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 5))
        self.progress_frame.pack(side="bottom", fill="x", padx=10, pady=5)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=5)
    
    def _browse_input(self):
        file_path = filedialog.askopenfilename(
            title="选择输入视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mkv *.mov *.flv *.wmv"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.input_var.set(file_path)
            if not self.output_var.get():
                base, ext = os.path.splitext(file_path)
                self.output_var.set(f"{base}_output{ext}")
            self._refresh_pipeline_preview()
    
    def _browse_output(self):
        file_path = filedialog.asksaveasfilename(
            title="选择输出文件",
            defaultextension=".mp4",
            filetypes=[
                ("MP4 文件", "*.mp4"),
                ("FLV 文件", "*.flv"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.output_var.set(file_path)
            self._refresh_pipeline_preview()

    def _browse_hls_output(self):
        file_path = filedialog.asksaveasfilename(
            title="选择 HLS 输出 m3u8 文件",
            defaultextension=".m3u8",
            filetypes=[
                ("HLS 播放列表", "*.m3u8"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            self.hls_output_var.set(file_path)
            self._refresh_pipeline_preview()
    
    def _on_preset_change(self):
        preset_key = self.preset_var.get()
        if preset_key == "custom":
            return
        
        preset = get_preset(preset_key)
        if preset:
            self._apply_config(preset.config)
    
    def _apply_config(self, config: EncodingConfig):
        self.video_profile_var.set(config.video.profile.value)
        self.video_resolution_var.set(config.video.resolution.value)
        self.video_encode_mode_var.set(config.video.encode_mode.value)
        self.video_bitrate_var.set(config.video.bitrate)
        self.video_max_bitrate_var.set(config.video.max_bitrate)
        self.video_keyint_var.set(config.video.keyint)
        self.video_bframes_var.set(config.video.bframes)
        self.video_ref_var.set(config.video.ref_frames)
        self.container_var.set(config.container.value)
        self.transport_var.set(config.transport.value)
        self.rtmp_url_var.set(config.rtmp_publish_url)
        self.hls_output_var.set(config.hls_playlist_path or "")
        self._update_transport_field_states()
        
        self.audio_enabled_var.set(config.audio.enabled)
        self.audio_codec_var.set(config.audio.codec.value)
        self.audio_bitrate_var.set(config.audio.bitrate)
        self.audio_sample_rate_var.set(config.audio.sample_rate)
        self.audio_ms_stereo_var.set(config.audio.ms_stereo)
        self.audio_lufs_var.set(config.audio.loudness_target_lufs)
        self.audio_side_reduce_var.set(config.audio.side_channel_reduce_db)
        self.audio_compression_ratio_var.set(config.audio.dynamic_compression_ratio)
        self.audio_high_pass_var.set(config.audio.high_pass_filter)
        
        self.double_encode_var.set(config.effects.double_encode.enabled)
        self.double_encode_res_var.set(config.effects.double_encode.first_pass_resolution.value)
        
        self.color_space_mode_var.set(config.effects.color_space.mode.value)
        self.color_space_auto_legacy_var.set(config.effects.color_space.auto_apply_legacy_flash_simulation)
        self.color_space_saturation_var.set(config.effects.color_space.saturation_adjust)
        self.color_space_contrast_var.set(config.effects.color_space.contrast_adjust)
        self.color_space_gamma_var.set(config.effects.color_space.gamma_adjust)
        self._update_color_space_parameter_states()
        self._refresh_pipeline_preview()
    
    def _get_current_config(self) -> EncodingConfig:
        profile_map = {
            "baseline": VideoProfile.BASELINE,
            "main": VideoProfile.MAIN,
            "high": VideoProfile.HIGH,
        }
        
        resolution_map = {
            "240p": ResolutionPreset.P240,
            "360p": ResolutionPreset.P360,
            "480p": ResolutionPreset.P480,
            "720p": ResolutionPreset.P720,
        }
        
        audio_codec_map = {
            "he-aac": AudioCodec.HE_AAC_V1,
            "aac-lc": AudioCodec.AAC_LC,
        }
        
        deint_method_map = {
            "yadif": DeinterlaceMethod.YADIF,
            "yadif=1": DeinterlaceMethod.BOB,
            "discard": DeinterlaceMethod.DISCARD,
        }
        
        return EncodingConfig(
            video=VideoConfig(
                profile=profile_map[self.video_profile_var.get()],
                resolution=resolution_map[self.video_resolution_var.get()],
                encode_mode=EncodeMode.ONE_PASS_ABR if self.video_encode_mode_var.get() == "1pass" else EncodeMode.TWO_PASS_VBR,
                bitrate=self.video_bitrate_var.get(),
                max_bitrate=self.video_max_bitrate_var.get(),
                keyint=self.video_keyint_var.get(),
                bframes=self.video_bframes_var.get(),
                ref_frames=self.video_ref_var.get(),
            ),
            audio=AudioConfig(
                enabled=self.audio_enabled_var.get(),
                codec=audio_codec_map[self.audio_codec_var.get()],
                bitrate=self.audio_bitrate_var.get(),
                sample_rate=self.audio_sample_rate_var.get(),
                ms_stereo=self.audio_ms_stereo_var.get(),
                side_channel_reduce_db=self.audio_side_reduce_var.get(),
                dynamic_compression_ratio=self.audio_compression_ratio_var.get(),
                loudness_target_lufs=self.audio_lufs_var.get(),
                high_pass_filter=self.audio_high_pass_var.get(),
            ),
            effects=EffectsConfig(
                preprocess=PreprocessConfig(
                    enabled=self.denoise_var.get() or self.deinterlace_var.get() or self.sharpen_var.get() or self.contrast_var.get() or self.saturation_var.get(),
                    denoise_enabled=self.denoise_var.get(),
                    denoise_strength=self.denoise_strength_var.get(),
                    deinterlace_enabled=self.deinterlace_var.get(),
                    deinterlace_method=deint_method_map[self.deinterlace_method_var.get()],
                    sharpen_enabled=self.sharpen_var.get(),
                    sharpen_strength=self.sharpen_strength_var.get(),
                    contrast_enabled=self.contrast_var.get(),
                    contrast_value=self.contrast_value_var.get(),
                    saturation_enabled=self.saturation_var.get(),
                    saturation_value=self.saturation_value_var.get(),
                ),
                double_encode=DoubleEncodeConfig(
                    enabled=self.double_encode_var.get(),
                    first_pass_resolution=resolution_map[self.double_encode_res_var.get()],
                ),
                color_space=ColorSpaceConfig(
                    mode=ColorSpaceMode(self.color_space_mode_var.get()),
                    auto_apply_legacy_flash_simulation=self.color_space_auto_legacy_var.get(),
                    saturation_adjust=self.color_space_saturation_var.get(),
                    contrast_adjust=self.color_space_contrast_var.get(),
                    gamma_adjust=self.color_space_gamma_var.get(),
                ),
            ),
            container=ContainerFormat.FLV if self.container_var.get() == "flv" else ContainerFormat.MP4,
            transport=TransportProtocol(self.transport_var.get()),
            rtmp_publish_url=self.rtmp_url_var.get().strip() or "rtmp://localhost/live/syrmetroize",
            hls_playlist_path=self.hls_output_var.get().strip() or None,
        )
    
    def _update_progress(self, step: str, progress: float):
        self.status_var.set(f"{step}: {progress*100:.1f}%")
        self.progress_var.set(progress * 100)
        self.root.update_idletasks()

    def _on_transport_change(self, *args):
        self._update_transport_field_states()
        self._refresh_pipeline_preview()

    def _on_container_change(self, *args):
        self._sync_output_extension_with_container()
        self._refresh_pipeline_preview()

    def _on_mode_related_change(self, *args):
        self._update_color_space_parameter_states()
        self._refresh_pipeline_preview()

    def _update_transport_field_states(self):
        transport = self.transport_var.get()
        rtmp_state = "normal" if transport == "rtmp" else "disabled"
        hls_state = "normal" if transport == "hls" else "disabled"

        if hasattr(self, "rtmp_url_entry"):
            self.rtmp_url_entry.configure(state=rtmp_state)
        if hasattr(self, "hls_output_entry"):
            self.hls_output_entry.configure(state=hls_state)
        if hasattr(self, "hls_output_browse_btn"):
            self.hls_output_browse_btn.configure(state=hls_state)

    def _sync_output_extension_with_container(self):
        output = self.output_var.get().strip()
        if not output:
            return

        wanted_ext = ".flv" if self.container_var.get() == "flv" else ".mp4"
        base, ext = os.path.splitext(output)
        if ext.lower() == wanted_ext:
            return

        if ext.lower() in {".mp4", ".flv"}:
            self.output_var.set(base + wanted_ext)

    def _update_color_space_parameter_states(self):
        mode = self.color_space_mode_var.get() if hasattr(self, "color_space_mode_var") else "none"
        enabled = mode == "simulation"
        state = "normal" if enabled else "disabled"

        if hasattr(self, "color_space_saturation_scale"):
            self.color_space_saturation_scale.configure(state=state)
        if hasattr(self, "color_space_contrast_scale"):
            self.color_space_contrast_scale.configure(state=state)
        if hasattr(self, "color_space_gamma_scale"):
            self.color_space_gamma_scale.configure(state=state)

        if hasattr(self, "color_param_hint_var"):
            if mode == "simulation":
                self.color_param_hint_var.set("以下参数在“模拟”模式生效")
            elif mode == "error_mapping":
                self.color_param_hint_var.set("当前为“错误映射”：以下参数不会生效")
            else:
                self.color_param_hint_var.set("当前未启用色彩处理")

    def _refresh_pipeline_preview(self):
        if not hasattr(self, "preview_text"):
            return

        container = getattr(self, "container_var", tk.StringVar(value="mp4")).get()
        transport = getattr(self, "transport_var", tk.StringVar(value="http")).get()
        color_mode = getattr(self, "color_space_mode_var", tk.StringVar(value="none")).get()
        output = self.output_var.get().strip() if hasattr(self, "output_var") else ""

        if color_mode == "simulation":
            color_desc = "2) 色彩处理: 模拟模式，Saturation/Contrast/Gamma 参数会生效（速度会明显变慢）。"
        elif color_mode == "error_mapping":
            color_desc = "2) 色彩处理: 错误映射模式，Saturation/Contrast/Gamma 参数不会生效（固定映射逻辑）。"
        else:
            color_desc = "2) 当前未开启色彩处理，速度更快。"

        lines = [
            "1) 先做视频编码与音频处理，再合并。",
            color_desc,
            f"3) 当前封装格式: {container.upper()}。",
        ]

        if container == "flv" and color_mode != "none":
            lines.append("4) 兼容性提示: FLV + 色彩处理会引发编码器兼容问题，建议改为 MP4。")
        else:
            lines.append("4) 当前组合兼容性正常。")

        if transport == "rtmp":
            lines.append(f"5) 传输: RTMP 推流到 {self.rtmp_url_var.get().strip() or 'rtmp://localhost/live/syrmetroize'}。")
        elif transport == "hls":
            hls_path = self.hls_output_var.get().strip() or "<自动生成 *_hls/index.m3u8>"
            lines.append(f"5) 传输: 生成 HLS 播放列表到 {hls_path}。")
        else:
            lines.append("5) 传输: HTTP 渐进下载（直接使用输出文件）。")

        if output:
            lines.append(f"6) 最终输出路径: {output}")

        content = "\n".join(lines)
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", content)
        self.preview_text.configure(state="disabled")

    def _setup_drag_drop(self):
        if not self._drag_drop_available:
            return

        drop_bindings = [
            (self.root, self._on_drop_to_input),
            (self.file_frame, self._on_drop_to_input),
            (self.input_entry, self._on_drop_to_input),
            (self.output_entry, self._on_drop_to_output),
        ]

        for widget, handler in drop_bindings:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", handler)
            except Exception:
                continue

    def _extract_drop_paths(self, data: str) -> list:
        try:
            values = list(self.root.tk.splitlist(data))
        except tk.TclError:
            values = data.split()

        paths = []
        for value in values:
            cleaned = value.strip().strip("{}")
            if not cleaned:
                continue
            paths.append(os.path.normpath(cleaned))
        return paths

    def _pick_first_existing_file(self, paths: list) -> Optional[str]:
        for path in paths:
            if os.path.isfile(path):
                return path
        return None

    def _on_drop_to_input(self, event):
        file_path = self._pick_first_existing_file(self._extract_drop_paths(event.data))
        if not file_path:
            return

        self.input_var.set(file_path)
        if not self.output_var.get():
            base, ext = os.path.splitext(file_path)
            self.output_var.set(f"{base}_output{ext}")

    def _on_drop_to_output(self, event):
        file_path = self._pick_first_existing_file(self._extract_drop_paths(event.data))
        if not file_path:
            return
        self.output_var.set(file_path)
    
    def _handle_error(self, error: str):
        messagebox.showerror("编码错误", f"编码过程中发生错误:\n{error}")
    
    def _start_encoding(self):
        input_file = self.input_var.get()
        output_file = self.output_var.get()
        
        if not input_file:
            messagebox.showwarning("警告", "请选择输入文件")
            return
        
        if not output_file:
            messagebox.showwarning("警告", "请选择输出文件")
            return
        
        if not os.path.exists(input_file):
            messagebox.showerror("错误", "输入文件不存在")
            return

        color_mode = self.color_space_mode_var.get()
        if self.container_var.get() == "flv" and color_mode != "none":
            switch_to_mp4 = messagebox.askyesno(
                "兼容性提示",
                "你当前选择了 FLV + 色彩处理。\n\n"
                "该组合在当前版本会因为编码器兼容问题导致失败。\n"
                "是否自动切换为 MP4 封装并继续？"
            )
            if not switch_to_mp4:
                return

            self.container_var.set("mp4")
            self._sync_output_extension_with_container()
            output_file = self.output_var.get()
            self._refresh_pipeline_preview()
        
        self.is_encoding = True
        self.start_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.progress_var.set(0)
        self.status_var.set("正在编码...")
        
        config = self._get_current_config()
        
        def encode_thread():
            try:
                self.pipeline = EncodingPipeline(
                    ffmpeg_path=self.ffmpeg_path,
                    progress_callback=self._update_progress,
                    error_callback=self._handle_error
                )
                
                success = self.pipeline.encode(input_file, output_file, config)
                
                self.root.after(0, lambda: self._encoding_complete(success))
            except Exception as e:
                self.root.after(0, lambda: self._handle_error(str(e)))
                self.root.after(0, lambda: self._encoding_complete(False))
        
        thread = threading.Thread(target=encode_thread, daemon=True)
        thread.start()
    
    def _encoding_complete(self, success: bool):
        self.is_encoding = False
        self.start_btn.config(state="normal")
        self.cancel_btn.config(state="disabled")
        
        if success:
            self.status_var.set("编码完成!")
            messagebox.showinfo("完成", "视频编码已完成!")
        else:
            self.status_var.set("编码已取消或失败")
    
    def _cancel_encoding(self):
        if self.pipeline:
            self.pipeline.cancel()
        self.status_var.set("正在取消...")
    
    def run(self):
        self.root.mainloop()
