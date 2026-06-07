import re
import os
import sys
import threading
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.colorchooser import askcolor
import tkinter.font as tkfont


def get_ffmpeg_path():
    """返回 ffmpeg 可执行文件路径（跨平台）。
    打包后优先使用随程序一起分发的内置 ffmpeg（Windows 为 ffmpeg.exe，
    macOS/Linux 为 ffmpeg）；若未内置则回退到系统 PATH 中的 ffmpeg。"""
    exe_name = 'ffmpeg.exe' if os.name == 'nt' else 'ffmpeg'
    if getattr(sys, 'frozen', False):
        base = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        bundled = os.path.join(base, exe_name)
        if os.path.exists(bundled):
            return bundled
    return 'ffmpeg'

# ==================== ASS 核心轉換邏輯 ====================
def srt_time_to_secs(t_str):
    t_str = t_str.strip().replace('.', ',')
    if ',' in t_str:
        main, ms = t_str.split(',')
    else:
        main = t_str
        ms = '0'
    
    parts = main.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, '0')[:3]) / 1000.0
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + int(s) + int(ms.ljust(3, '0')[:3]) / 1000.0
    return 0.0

def to_ass_time(secs):
    if secs < 0: secs = 0
    h = int(secs // 3600)
    m = int((secs % 3600) // 60)
    s = int(secs % 60)
    cs = int(round((secs - int(secs)) * 100))
    if cs == 100:
        s += 1
        cs = 0
        if s == 60:
            m += 1
            s = 0
            if m == 60:
                h += 1
                m = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def parse_srt(srt_path):
    content = ""
    # 依序嘗試多種主流編碼讀取，徹底解決來源檔案編碼引起的亂碼問題
    for enc in ['utf-8-sig', 'utf-8', 'gbk', 'utf-16', 'big5']:
        try:
            with open(srt_path, 'r', encoding=enc) as f:
                content = f.read().replace('\r\n', '\n')
            break
        except Exception:
            continue
            
    if not content:
        try:
            with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read().replace('\r\n', '\n')
        except Exception:
            pass

    blocks = content.strip().split('\n\n')
    subs = []
    for block in blocks:
        lines = [l.strip() for l in block.split('\n') if l.strip()]
        if len(lines) >= 2:
            time_line = ""
            text_idx = 1
            for idx, line in enumerate(lines):
                if "-->" in line:
                    time_line = line
                    text_idx = idx + 1
                    break
            
            if time_line:
                text = " ".join(lines[text_idx:])
                match = re.search(r'(\d+:\d+:\d+[\.,]\d+)\s+-->\s+(\d+:\d+:\d+[\.,]\d+)', time_line)
                if match:
                    subs.append({
                        'start': srt_time_to_secs(match.group(1)),
                        'end': srt_time_to_secs(match.group(2)),
                        'text': text
                    })
    return subs

def hex_to_ass_color(hex_str):
    hex_str = hex_str.lstrip('#')
    r = hex_str[0:2]
    g = hex_str[2:4]
    b = hex_str[4:6]
    return f"&H{b}{g}{r}&"

def core_converter(srt_path, ass_path, font_name, fs_hl, fs_norm, row_gap, hl_color_ass, normal_color_ass, width, height):
    subs = parse_srt(srt_path)
    if not subs:
        raise ValueError("未检测到任何兼容的 SRT 字幕内容，或文件编码完全损坏。")

    TRANS_DURATION = 0.38
    
    fs_0 = fs_hl
    fs_1 = fs_norm
    fs_2 = int(fs_norm * 0.8) if int(fs_norm * 0.8) > 10 else 10
    fs_3 = int(fs_norm * 0.6) if int(fs_norm * 0.6) > 10 else 10

    y_center = int(height * 0.52)
    x_center = width // 2

    extended_slots = {
        -3: {'y': y_center - 3 * row_gap, 'fs': fs_3, 'tags': f'\\c{normal_color_ass}\\1a&HFF&'},
        -2: {'y': y_center - 2 * row_gap, 'fs': fs_2, 'tags': f'\\c{normal_color_ass}\\1a&HA0&'},
        -1: {'y': y_center - 1 * row_gap, 'fs': fs_1, 'tags': f'\\c{normal_color_ass}\\1a&H40&'},
         0: {'y': y_center,                 'fs': fs_0, 'tags': f'\\c{hl_color_ass}\\1a&H00&'},  
         1: {'y': y_center + 1 * row_gap, 'fs': fs_1, 'tags': f'\\c{normal_color_ass}\\1a&H40&'},
         2: {'y': y_center + 2 * row_gap, 'fs': fs_2, 'tags': f'\\c{normal_color_ass}\\1a&HA0&'},
         3: {'y': y_center + 3 * row_gap, 'fs': fs_3, 'tags': f'\\c{normal_color_ass}\\1a&HFF&'}
    }

    ass_header = f"""[Script Info]
Title: Apple Music Video Adaptive Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},60,&H00FFFFFF&,&H00000000&,&H00000000&,&H00000000&,1,0,0,0,100,100,0,0,1,0,0,5,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    timeline = []
    timeline.append({'start': 0.0, 'end': subs[0]['start'], 'active_idx': -1, 'is_trans': False})

    for i in range(len(subs)):
        t_start = subs[i]['start']
        t_end = subs[i+1]['start'] if i < len(subs)-1 else subs[i]['end'] + 2.0
        t_trans_end = min(t_start + TRANS_DURATION, t_end)
        
        timeline.append({
            'start': t_start, 'end': t_trans_end, 
            'active_idx': i, 'is_trans': True, 'trans_len': t_trans_end - t_start
        })
        if t_trans_end < t_end:
            timeline.append({
                'start': t_trans_end, 'end': t_end, 
                'active_idx': i, 'is_trans': False
            })

    events = []
    for state in timeline:
        t_s_str = to_ass_time(state['start'])
        t_e_str = to_ass_time(state['end'])
        if t_s_str == t_e_str:
            continue
            
        act = state['active_idx']
        
        for idx in range(len(subs)):
            s_curr = idx - act
            s_prev = idx - (act - 1) if state['is_trans'] else s_curr
                
            if (-3 <= s_curr <= 3) or (-3 <= s_prev <= 3):
                s_curr_clamped = max(-3, min(3, s_curr))
                s_prev_clamped = max(-3, min(3, s_prev))
                
                if s_curr_clamped == 3 and s_prev_clamped == 3: continue
                if s_curr_clamped == -3 and s_prev_clamped == -3: continue
                
                text = subs[idx]['text']
                
                if state['is_trans'] and s_prev_clamped != s_curr_clamped:
                    y_prev = extended_slots[s_prev_clamped]['y']
                    y_curr = extended_slots[s_curr_clamped]['y']
                    fs_prev = extended_slots[s_prev_clamped]['fs']
                    fs_curr = extended_slots[s_curr_clamped]['fs']
                    tags_prev = extended_slots[s_prev_clamped]['tags']
                    tags_curr = extended_slots[s_curr_clamped]['tags']
                    trans_ms = int(state['trans_len'] * 1000)
                    
                    ass_line = (
                        f"Dialogue: 0,{t_s_str},{t_e_str},Default,,0,0,0,,"
                        f"{{\\an5\\move({x_center},{y_prev},{x_center},{y_curr},0,{trans_ms}){tags_prev}\\fs{fs_prev}"
                        f"\\t(0,{trans_ms},{tags_curr}\\fs{fs_curr})}}{text}"
                    )
                else:
                    y_curr = extended_slots[s_curr_clamped]['y']
                    fs_curr = extended_slots[s_curr_clamped]['fs']
                    tags_curr = extended_slots[s_curr_clamped]['tags']
                    
                    ass_line = (
                        f"Dialogue: 0,{t_s_str},{t_e_str},Default,,0,0,0,,"
                        f"{{\\an5\\pos({x_center},{y_curr}){tags_curr}\\fs{fs_curr}}}{text}"
                    )
                    
                events.append(ass_line)

    with open(ass_path, "w", encoding="utf-8-sig") as f:
        f.write(ass_header + "\n".join(events))
        
    return subs[-1]['end'] + 3.0

# ==================== GUI 介面設計 ====================
class AppMusicLyricsApp:
    # 默认示例歌词（未载入 SRT 时使用，7 行对应 slot -3 ~ +3）
    _DEFAULT_LYRICS = [
        "时光似流水",
        "悄悄地离去",
        "往事如风消散",
        "此刻只剩回忆",
        "心中那份思念",
        "仍未曾褪去",
        "等你归来",
    ]
    _PREVIEW_BG = "#0a0a0a"
    _TRANS_DURATION = 0.38   # 行切換過渡時間（秒），與 ASS 輸出保持一致

    def __init__(self, root):
        self.root = root
        self.root.title("Apple Music 滚动字幕与视频生成器 v2.2")
        self.root.geometry("1140x780")
        self.root.resizable(True, True)
        self.root.minsize(960, 660)

        self.hl_color     = "#FFFFFF"
        self.normal_color = "#808080"
        self.bg_color     = "#000000"

        # ---- 預覽相關狀態 ----
        self.srt_subs = []          # 已載入的 SRT 字幕條目（[{start,end,text}, ...]）
        self.preview_time = 0.0     # 進度條當前時間（秒）
        self.preview_total = 30.0   # 進度條總長度（秒），有 SRT 時根據實際結束時間更新

        # 未載入 SRT 時使用的示範字幕（帶時間軸，按播放鍵即可上下滾動預覽）
        self.demo_subs = []
        _t0 = 0.0
        for _line in self._DEFAULT_LYRICS:
            self.demo_subs.append({'start': _t0, 'end': _t0 + 2.0, 'text': _line})
            _t0 += 2.0

        # ---- 播放控制狀態 ----
        self.is_playing = False             # 預覽是否正在播放
        self._play_after_id = None          # after() 回調 id（用於取消播放）
        self._play_interval_ms = 33         # 播放刷新間隔（≈30fps，動畫更順）
        self._play_step = self._play_interval_ms / 1000.0  # 每次推進的秒數（=實時播放）

        # 預覽渲染上下文（背景只在尺寸/配置變化時重繪，播放時僅重繪文字以保證流暢）
        self._render_ctx = None

        # ---- 字體列表構建 ----
        raw_fonts = list(set(tkfont.families(root)))
        all_fonts = [f for f in raw_fonts if f and not f.startswith('@')]

        def _is_cjk_font(name):
            for ch in name:
                cp = ord(ch)
                if (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
                        0xF900 <= cp <= 0xFAFF or 0x3000 <= cp <= 0x303F):
                    return True
            cjk_keywords = [
                'yahei', 'jhenghei', 'simsun', 'simhei', 'simkai', 'nsimsun',
                'fangsong', 'kaiti', 'dengxian', 'youyuan', 'lishu',
                'stzhongsong', 'stkaiti', 'stheiti', 'stfangsong', 'stsong',
                'pmingliu', 'mingliu', 'heiti', 'songti', 'weibei', 'xingkai',
                'yuanti', 'wawati', 'lantinghei', 'hanzipen', 'hannotate',
                'libian', 'lisung', 'ligothic', 'hiragino', 'meiryo',
                'ms gothic', 'ms mincho', 'yu gothic', 'malgun', 'batang',
                'gungsuh', 'dotum', 'gulim', 'noto sans cjk', 'noto serif cjk',
                'source han',
            ]
            lower = name.lower()
            return any(kw in lower for kw in cjk_keywords)

        chinese_fonts     = sorted([f for f in all_fonts if _is_cjk_font(f)])
        other_fonts       = sorted([f for f in all_fonts if not _is_cjk_font(f)])
        self.system_fonts = chinese_fonts + other_fonts

        default_font  = ""
        preferred_fonts = ["微軟正黑體", "Microsoft JhengHei", "微软雅黑", "Microsoft YaHei",
                           "新細明體", "PMingLiU", "SimHei", "黑体",
                           # macOS 常见中文字体
                           "PingFang SC", "苹方-简", "Heiti SC", "黑体-简",
                           "STHeiti", "Hiragino Sans GB", "Arial Unicode MS",
                           "Arial"]
        for pf in preferred_fonts:
            if pf in self.system_fonts:
                default_font = pf
                break
        if not default_font and self.system_fonts:
            default_font = self.system_fonts[0]

        # ======== 主佈局：左側控制 | 右側預覽 ========
        main_frame = tk.Frame(root)
        main_frame.pack(fill="both", expand=True)

        # 右側預覽面板（隨視窗縮放佔據剩餘空間，預覽跟著放大縮小）
        right_panel = tk.Frame(main_frame, bg="#161616", width=500)
        right_panel.pack(side="right", fill="both", expand=True)
        right_panel.pack_propagate(False)

        # 垂直分割線
        tk.Frame(main_frame, width=1, bg="#3a3a3a").pack(side="right", fill="y")

        # 左側控制面板
        left_panel = tk.Frame(main_frame)
        left_panel.pack(side="left", fill="y")

        # ---- 1. 文件选择 ----
        frame_file = ttk.LabelFrame(left_panel, text=" 1. 文件选择 ", padding=10)
        frame_file.pack(fill="x", padx=15, pady=5)

        ttk.Label(frame_file, text="SRT 文件:").grid(row=0, column=0, sticky="w")
        self.entry_srt = ttk.Entry(frame_file, width=28)
        self.entry_srt.grid(row=0, column=1, sticky="w", padx=5, pady=2)
        ttk.Button(frame_file, text="浏览...", command=self.select_srt).grid(row=0, column=2, padx=2)

        # ---- 2. 字体与间距 ----
        frame_cfg = ttk.LabelFrame(left_panel, text=" 2. 字体与间距配置 ", padding=10)
        frame_cfg.pack(fill="x", padx=15, pady=5)

        ttk.Label(frame_cfg, text="字体选择:").grid(row=0, column=0, sticky="w", pady=5)
        self.combo_font = ttk.Combobox(frame_cfg, values=self.system_fonts, width=28, state="readonly")
        self.combo_font.grid(row=0, column=1, sticky="w", padx=5, pady=5)
        if default_font:
            self.combo_font.set(default_font)
        self.combo_font.bind("<<ComboboxSelected>>", self.update_preview)

        ttk.Label(frame_cfg, text="高亮字号:").grid(row=1, column=0, sticky="w", pady=5)
        self.scale_fs_hl = ttk.Scale(frame_cfg, from_=30, to=150, value=76, command=self.update_labels)
        self.scale_fs_hl.grid(row=1, column=1, sticky="we", padx=5)
        self.entry_fs_hl = ttk.Entry(frame_cfg, width=5, justify="center")
        self.entry_fs_hl.insert(0, "76")
        self.entry_fs_hl.grid(row=1, column=2, sticky="w", padx=(4, 1))
        ttk.Label(frame_cfg, text="px").grid(row=1, column=3, sticky="w")
        self._bind_entry_to_scale(self.entry_fs_hl, self.scale_fs_hl, 30, 150)

        ttk.Label(frame_cfg, text="非高亮字号:").grid(row=2, column=0, sticky="w", pady=5)
        self.scale_fs_norm = ttk.Scale(frame_cfg, from_=20, to=120, value=56, command=self.update_labels)
        self.scale_fs_norm.grid(row=2, column=1, sticky="we", padx=5)
        self.entry_fs_norm = ttk.Entry(frame_cfg, width=5, justify="center")
        self.entry_fs_norm.insert(0, "56")
        self.entry_fs_norm.grid(row=2, column=2, sticky="w", padx=(4, 1))
        ttk.Label(frame_cfg, text="px").grid(row=2, column=3, sticky="w")
        self._bind_entry_to_scale(self.entry_fs_norm, self.scale_fs_norm, 20, 120)

        ttk.Label(frame_cfg, text="行 间 距:").grid(row=3, column=0, sticky="w", pady=5)
        self.scale_gap = ttk.Scale(frame_cfg, from_=60, to=250, value=140, command=self.update_labels)
        self.scale_gap.grid(row=3, column=1, sticky="we", padx=5)
        self.entry_gap = ttk.Entry(frame_cfg, width=5, justify="center")
        self.entry_gap.insert(0, "140")
        self.entry_gap.grid(row=3, column=2, sticky="w", padx=(4, 1))
        ttk.Label(frame_cfg, text="px").grid(row=3, column=3, sticky="w")
        self._bind_entry_to_scale(self.entry_gap, self.scale_gap, 60, 250)

        ttk.Label(frame_cfg, text="分 辨 率:").grid(row=4, column=0, sticky="w", pady=5)
        self.combo_res = ttk.Combobox(
            frame_cfg,
            values=["1920x1080 (16:9 横屏)", "1080x1920 (9:16 竖屏)",
                    "2560x1440 (2K 横屏)", "3840x2160 (4K 横屏)"],
            width=28, state="readonly")
        self.combo_res.set("1920x1080 (16:9 横屏)")
        self.combo_res.grid(row=4, column=1, sticky="w", padx=5, pady=5)
        # 分辨率變更時，預覽比例需聯動更新
        self.combo_res.bind("<<ComboboxSelected>>", self.update_preview)

        # ---- 3. 歌词颜色 ----
        frame_color = ttk.LabelFrame(left_panel, text=" 3. 歌词颜色配置 ", padding=10)
        frame_color.pack(fill="x", padx=15, pady=5)

        ttk.Label(frame_color, text="高亮颜色:").grid(row=0, column=0, sticky="w", pady=5)
        self.btn_hl_color = tk.Button(frame_color, bg=self.hl_color, width=8,
                                      relief="groove", command=self.pick_hl_color)
        self.btn_hl_color.grid(row=0, column=1, padx=10, sticky="w")

        ttk.Label(frame_color, text="普通颜色:").grid(row=0, column=2, sticky="w", pady=5)
        self.btn_norm_color = tk.Button(frame_color, bg=self.normal_color, width=8,
                                        relief="groove", command=self.pick_norm_color)
        self.btn_norm_color.grid(row=0, column=3, padx=10, sticky="w")

        # ---- 4. 视频导出配置 ----
        self.frame_video = ttk.LabelFrame(left_panel, text=" 4. 视频导出配置 (依赖 FFmpeg) ", padding=10)
        self.frame_video.pack(fill="x", padx=15, pady=5)

        self.var_export_video = tk.BooleanVar(value=False)
        self.chk_video = ttk.Checkbutton(self.frame_video, text="开启视频输出功能",
                                          variable=self.var_export_video,
                                          command=self.toggle_video_widgets)
        self.chk_video.grid(row=0, column=0, columnspan=4, sticky="w", pady=2)

        ttk.Label(self.frame_video, text="帧率 (FPS):").grid(row=1, column=0, sticky="w", pady=5)
        self.combo_fps = ttk.Combobox(self.frame_video, values=["30", "60", "25"],
                                       width=8, state="readonly")
        self.combo_fps.set("60")
        self.combo_fps.grid(row=1, column=1, sticky="w", padx=5)

        # 透明背景开关：勾选→选「透明格式」，取消→选「视频体积」
        self.var_transparent = tk.BooleanVar(value=True)
        self.chk_trans = ttk.Checkbutton(
            self.frame_video, text="透明背景",
            variable=self.var_transparent, command=self.on_transparent_toggle)
        self.chk_trans.grid(row=2, column=0, columnspan=2, sticky="w", pady=8)

        # 透明格式（仅勾选透明背景时显示）——三种均带 alpha 通道
        self.lbl_fmt = ttk.Label(self.frame_video, text="透明格式:")
        self.combo_fmt = ttk.Combobox(
            self.frame_video,
            values=["ProRes 4444 (MOV·标准·体积大)",
                    "QuickTime RLE (MOV·无损·体积中)",
                    "VP9 (WebM·体积最小)"],
            width=24, state="readonly")
        self.combo_fmt.set("ProRes 4444 (MOV·标准·体积大)")

        # 视频体积（仅取消透明背景、输出实色视频时显示）
        self.lbl_size = ttk.Label(self.frame_video, text="视频体积:")
        self.combo_size = ttk.Combobox(
            self.frame_video,
            values=["高品质 (体积大)", "平衡 (推荐)", "高压缩 (体积小)"],
            width=24, state="readonly")
        self.combo_size.set("平衡 (推荐)")

        # 实色背景颜色（仅取消透明背景时显示）
        self.lbl_bg_btn_text = ttk.Label(self.frame_video, text="实色背景:")
        self.btn_bg_color = tk.Button(self.frame_video, bg=self.bg_color, width=8,
                                       relief="groove", command=self.pick_bg_color)

        self.toggle_video_widgets()

        # ---- 5. 生成按钮 ----
        self.btn_convert = ttk.Button(left_panel,
                                      text="🚀 一 键 生 成 A S S 字 幕 / 视 频",
                                      command=self.start_thread)
        self.btn_convert.pack(fill="x", padx=15, pady=15)

        # ======== 右侧预览面板内容 ========
        # 預覽容器（用於放置按比例縮放的 Canvas）
        self.preview_container = tk.Frame(right_panel, bg="#161616")
        self.preview_container.pack(fill="both", expand=True, padx=16, pady=(14, 8))

        # 真正的視頻預覽 Canvas（其尺寸由 update_preview 動態計算以匹配視頻比例）
        self.preview_canvas = tk.Canvas(
            self.preview_container, bg=self._PREVIEW_BG,
            highlightthickness=1, highlightbackground="#2e2e2e", bd=0)
        # 使用 place 居中，尺寸由 update_preview 設定
        self.preview_canvas.place(relx=0.5, rely=0.5, anchor="center", width=10, height=10)

        # 進度條與時間顯示
        progress_frame = tk.Frame(right_panel, bg="#161616")
        progress_frame.pack(fill="x", padx=16, pady=(4, 14))

        self.btn_play = tk.Button(progress_frame, text="▶", width=3,
                                  bg="#2a2a2a", fg="#dddddd",
                                  activebackground="#3a3a3a", activeforeground="#ffffff",
                                  relief="flat", command=self.toggle_play)
        self.btn_play.pack(side="left", padx=(0, 8))

        self.lbl_time_cur = tk.Label(progress_frame, text="00:00.0",
                                     bg="#161616", fg="#bdbdbd",
                                     font=("Consolas", 9))
        self.lbl_time_cur.pack(side="left")

        self.lbl_time_total = tk.Label(progress_frame, text=" / 00:30.0",
                                       bg="#161616", fg="#777777",
                                       font=("Consolas", 9))
        self.lbl_time_total.pack(side="right")

        self.scale_progress = ttk.Scale(
            progress_frame, from_=0.0, to=self.preview_total,
            orient="horizontal", value=0.0,
            command=self.on_progress_change)
        self.scale_progress.pack(side="left", fill="x", expand=True, padx=8)

        # 啟動時即以示範字幕設定進度條總長度
        self._update_progress_range_from_srt()

        # 容器尺寸變化時重新繪製（保持比例）
        self.preview_container.bind("<Configure>", lambda e: self.update_preview())

        # 延遲首次渲染，等視窗尺寸確定後再執行
        root.after(80, self.update_preview)

    # ---- 顏色混合工具 ----
    @staticmethod
    def _blend_color(fg: str, bg: str, opacity: float) -> str:
        """將前景色以 opacity 疊加到背景色上（opacity: 0=透明, 1=不透明）。"""
        fr, fg_, fb = int(fg[1:3], 16), int(fg[3:5], 16), int(fg[5:7], 16)
        br, bg_, bb = int(bg[1:3], 16), int(bg[3:5], 16), int(bg[5:7], 16)
        r = int(opacity * fr + (1 - opacity) * br)
        g = int(opacity * fg_ + (1 - opacity) * bg_)
        b = int(opacity * fb + (1 - opacity) * bb)
        return f"#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _lerp_color(c1: str, c2: str, p: float) -> str:
        """在兩個 #RRGGBB 顏色之間線性插值（p: 0=c1, 1=c2）。"""
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        r = int(r1 + (r2 - r1) * p)
        g = int(g1 + (g2 - g1) * p)
        b = int(b1 + (b2 - b1) * p)
        return f"#{r:02x}{g:02x}{b:02x}"

    # ---- 解析當前選擇的視頻分辨率 ----
    def _get_target_resolution(self):
        try:
            res_str = self.combo_res.get().split(" ")[0]
            w, h = map(int, res_str.split("x"))
            return w, h
        except Exception:
            return 1920, 1080

    @staticmethod
    def _fmt_time(secs: float) -> str:
        if secs < 0: secs = 0
        m = int(secs // 60)
        s = secs - m * 60
        return f"{m:02d}:{s:04.1f}"

    # ---- 取得在 preview_time 時刻的播放狀態（含過渡進度，用於動畫插值）----
    def _get_active_state(self):
        """
        返回 (subs, active_idx, prog)
        - subs: 當前使用的字幕列表（SRT 或示範）
        - active_idx: 當前置中的行索引（無 SRT 時開場為 0）
        - prog: 0~1，表示由「上一排佈局」過渡到「當前佈局」的進度，用於平滑滾動
        """
        use_demo = not self.srt_subs
        subs = self.demo_subs if use_demo else self.srt_subs
        t = self.preview_time

        # 找到 active_idx：最後一個 start <= t 的條目
        active_idx = -1
        for i, s in enumerate(subs):
            if s['start'] <= t:
                active_idx = i
            else:
                break

        # 計算過渡進度
        if active_idx < 0:
            # 尚未進入第一行：靜止顯示（後續行在下方等待）
            prog = 1.0
            if use_demo:
                active_idx = 0          # 示範模式開場即把第一行置中
        elif use_demo and active_idx == 0:
            prog = 1.0                  # 示範第一行不做入場動畫，開場即穩定置中
        else:
            t_start = subs[active_idx]['start']
            prog = (t - t_start) / self._TRANS_DURATION
            prog = max(0.0, min(1.0, prog))

        return subs, active_idx, prog

    # ---- 進度條變化回調 ----
    def on_progress_change(self, value):
        try:
            self.preview_time = float(value)
        except Exception:
            self.preview_time = 0.0
        self.lbl_time_cur.config(text=self._fmt_time(self.preview_time))
        # 僅重繪文字（背景不變），保證播放/拖動進度時的流暢度
        self._redraw_lyrics()

    # ---- 播放 / 暫停控制 ----
    def toggle_play(self):
        if self.is_playing:
            self._stop_play()
        else:
            self._start_play()

    def _start_play(self):
        # 若已播放到結尾，從頭開始
        if self.preview_time >= self.preview_total - 1e-3:
            self.preview_time = 0.0
            self.scale_progress.set(0.0)
        self.is_playing = True
        self.btn_play.config(text="⏸")
        self._play_tick()

    def _stop_play(self):
        self.is_playing = False
        self.btn_play.config(text="▶")
        if self._play_after_id is not None:
            try:
                self.root.after_cancel(self._play_after_id)
            except Exception:
                pass
            self._play_after_id = None

    def _play_tick(self):
        if not self.is_playing:
            return
        new_t = self.preview_time + self._play_step
        if new_t >= self.preview_total:
            # 設定到結尾並停止（set 會觸發 on_progress_change 更新畫面）
            self.scale_progress.set(self.preview_total)
            self._stop_play()
            return
        # set 會觸發 on_progress_change，自動更新 preview_time、時間標籤與預覽
        self.scale_progress.set(new_t)
        self._play_after_id = self.root.after(self._play_interval_ms, self._play_tick)

    # ---- 預覽渲染 ----
    def update_preview(self, event=None):
        """根據當前字體、大小、顏色設置與視頻比例，重繪預覽畫布。"""
        container = self.preview_container
        cont_w = container.winfo_width()
        cont_h = container.winfo_height()
        if cont_w <= 1 or cont_h <= 1:
            self.root.after(60, self.update_preview)
            return

        # 視頻目標分辨率，預覽畫布按該比例顯示
        target_w, target_h = self._get_target_resolution()
        aspect = target_w / target_h

        # 在容器內以信箱模式適配 aspect
        avail_w = max(cont_w - 8, 50)
        avail_h = max(cont_h - 8, 50)
        if avail_w / avail_h > aspect:
            canvas_h = avail_h
            canvas_w = max(int(canvas_h * aspect), 50)
        else:
            canvas_w = avail_w
            canvas_h = max(int(canvas_w / aspect), 50)

        # 設定 canvas 尺寸並居中
        self.preview_canvas.place_configure(width=canvas_w, height=canvas_h)

        c = self.preview_canvas
        c.delete("all")
        cw, ch = canvas_w, canvas_h

        # ---- 背景（僅在此完整重繪時繪製一次；播放時不重繪以保證流暢）----
        if self.var_transparent.get():
            self._draw_checker(c, 0, 0, cw, ch, size=12)
        else:
            c.create_rectangle(0, 0, cw, ch, fill=self.bg_color, outline="")

        # 分辨率指示文字（左上角，靜態）
        res_label = f"{target_w}×{target_h}  ({'橫屏' if target_w >= target_h else '豎屏'})"
        c.create_text(8, 8, text=res_label, anchor="nw",
                      font=("Arial", 8), fill="#666666")

        font_name = self.combo_font.get() or "Arial"
        fs_hl   = int(self.scale_fs_hl.get())
        fs_norm = int(self.scale_fs_norm.get())
        row_gap = int(self.scale_gap.get())

        # 預覽縮放因子：直接基於視頻寬度映射，使預覽字號/間距比例完全匹配最終輸出
        scale = canvas_w / target_w

        # 將本次的幾何與樣式參數快取，供播放時僅重繪文字使用
        self._render_ctx = {
            'cx': cw // 2,
            'cy': int(ch * 0.52),   # 與 ASS 中保持一致：y_center = height * 0.52
            'cw': cw, 'ch': ch,
            'p_fs_hl':   max(8, int(fs_hl   * scale)),
            'p_fs_norm': max(7, int(fs_norm * scale)),
            'p_fs_2':    max(6, int(fs_norm * 0.8 * scale)),
            'p_fs_3':    max(5, int(fs_norm * 0.6 * scale)),
            'p_gap':     max(12, int(row_gap * scale)),
            'font_name': font_name,
            'bg_for_blend': "#0a0a0a" if self.var_transparent.get() else self.bg_color,
        }

        # 繪製歌詞文字
        self._redraw_lyrics()

    # ---- 僅重繪歌詞文字（不動背景），用於播放/拖動進度時的高效刷新 ----
    def _redraw_lyrics(self):
        ctx = self._render_ctx
        if not ctx:
            self.update_preview()
            return

        c = self.preview_canvas
        c.delete("lyric")   # 只刪除上一幀的文字，保留背景

        cx, cy = ctx['cx'], ctx['cy']
        cw, ch = ctx['cw'], ctx['ch']
        p_gap = ctx['p_gap']
        font_name = ctx['font_name']
        bg_for_blend = ctx['bg_for_blend']

        fs_by_slot = {-3: ctx['p_fs_3'], -2: ctx['p_fs_2'], -1: ctx['p_fs_norm'],
                       0: ctx['p_fs_hl'], 1: ctx['p_fs_norm'], 2: ctx['p_fs_2'],
                       3: ctx['p_fs_3']}
        op_by_slot = {-3: 0.0, -2: 1.0 - 160 / 255, -1: 1.0 - 64 / 255, 0: 1.0,
                       1: 1.0 - 64 / 255, 2: 1.0 - 160 / 255, 3: 0.0}

        def _fs(slot):
            return fs_by_slot[max(-3, min(3, slot))]

        def _op(slot):
            return op_by_slot[max(-3, min(3, slot))] if -3 <= slot <= 3 else 0.0

        def _slot_color(slot):
            base = self.hl_color if slot == 0 else self.normal_color
            return self._blend_color(base, bg_for_blend, max(0.0, min(1.0, _op(slot))))

        # 取得當前播放狀態：subs / active 行 / 過渡進度（0~1）
        subs, active_idx, prog = self._get_active_state()
        # 緩動，讓上下滾動更柔順（easeInOutQuad）
        ep = (2 * prog * prog) if prog < 0.5 else (1 - (-2 * prog + 2) ** 2 / 2)

        n = len(subs)
        # 逐行插值：每行從「上一排佈局(active-1)」過渡到「當前佈局(active)」
        for idx in range(max(0, active_idx - 4), min(n, active_idx + 5)):
            text = subs[idx]['text']
            if not text:
                continue
            slot_curr = idx - active_idx
            slot_prev = slot_curr + 1   # 過渡開始時 active 為 active_idx-1

            op = _op(slot_prev) + (_op(slot_curr) - _op(slot_prev)) * ep
            if op <= 0.01:
                continue

            y_prev = cy + slot_prev * p_gap
            y_curr = cy + slot_curr * p_gap
            y = y_prev + (y_curr - y_prev) * ep

            fs = _fs(slot_prev) + (_fs(slot_curr) - _fs(slot_prev)) * ep
            fsize = max(5, int(round(fs)))

            color = self._lerp_color(_slot_color(slot_prev), _slot_color(slot_curr), ep)

            # 超出畫布範圍的條目跳過
            if y < -fsize or y > ch + fsize:
                continue
            c.create_text(cx, y, text=text,
                          font=(font_name, -fsize),
                          fill=color, anchor="center",
                          width=int(cw * 0.92), tags="lyric")

    @staticmethod
    def _draw_checker(canvas, x0, y0, x1, y1, size=12):
        """在 canvas 指定區域繪製棋盤格背景，用以表示透明區域。"""
        c1, c2 = "#2a2a2a", "#1b1b1b"
        canvas.create_rectangle(x0, y0, x1, y1, fill=c1, outline="")
        for yy in range(y0, y1, size):
            for xx in range(x0, x1, size):
                if ((xx // size) + (yy // size)) % 2 == 0:
                    canvas.create_rectangle(xx, yy,
                                            min(xx + size, x1),
                                            min(yy + size, y1),
                                            fill=c2, outline="")

    # ---- 載入並解析 SRT 後更新預覽進度條 ----
    def _update_progress_range_from_srt(self):
        if self.srt_subs:
            last_end = self.srt_subs[-1].get('end', 0.0) or 0.0
            total = max(last_end + 2.0, 5.0)
        else:
            # 未載入 SRT：使用示範字幕的時間長度，使播放可滾動到最後一行
            total = (self.demo_subs[-1]['end'] + 2.0) if self.demo_subs else 30.0
        self.preview_total = total
        # 重設進度條
        self.scale_progress.config(from_=0.0, to=total)
        self.preview_time = 0.0
        self.scale_progress.set(0.0)
        self.lbl_time_cur.config(text=self._fmt_time(0.0))
        self.lbl_time_total.config(text=f" / {self._fmt_time(total)}")

    def select_srt(self):
        file_path = filedialog.askopenfilename(filetypes=[("SRT Subtitles", "*.srt")])
        if not file_path:
            return
        self.entry_srt.delete(0, tk.END)
        self.entry_srt.insert(0, file_path)

        # 解析並載入到預覽
        try:
            subs = parse_srt(file_path)
        except Exception:
            subs = []
        self.srt_subs = subs

        # 載入新字幕時若正在播放，先停止並重置進度
        self._stop_play()
        self._update_progress_range_from_srt()
        self.update_preview()

    def update_labels(self, event=None):
        self._set_entry(self.entry_fs_hl, int(self.scale_fs_hl.get()))
        self._set_entry(self.entry_fs_norm, int(self.scale_fs_norm.get()))
        self._set_entry(self.entry_gap, int(self.scale_gap.get()))
        self.update_preview()

    @staticmethod
    def _set_entry(entry, value):
        """將輸入框內容同步為指定整數（避免重複寫入造成游標跳動）。"""
        if entry.get().strip() == str(value):
            return
        entry.delete(0, tk.END)
        entry.insert(0, str(value))

    def _bind_entry_to_scale(self, entry, scale, vmin, vmax):
        """讓輸入框支援鍵盤輸入：Enter 或失焦時讀取數值、夾在範圍內並同步滑塊。"""
        def handler(event=None):
            raw = entry.get().strip()
            try:
                v = int(round(float(raw)))
            except Exception:
                v = int(scale.get())  # 輸入非法則還原為當前值
            v = max(vmin, min(vmax, v))
            # scale.set 會觸發 update_labels，自動回寫夾過範圍的數值並刷新預覽
            scale.set(v)
            return "break"
        entry.bind("<Return>", handler)
        entry.bind("<FocusOut>", handler)

    def pick_hl_color(self):
        color = askcolor(title="选择高亮歌词颜色", color=self.hl_color)
        if color[1]:
            self.hl_color = color[1]
            self.btn_hl_color.config(bg=self.hl_color)
            self.update_preview()

    def pick_norm_color(self):
        color = askcolor(title="选择普通歌词颜色", color=self.normal_color)
        if color[1]:
            self.normal_color = color[1]
            self.btn_norm_color.config(bg=self.normal_color)
            self.update_preview()

    def pick_bg_color(self):
        color = askcolor(title="选择自定背景颜色", color=self.bg_color)
        if color[1]:
            self.bg_color = color[1]
            self.btn_bg_color.config(bg=self.bg_color)
            self.update_preview()

    def toggle_video_widgets(self):
        # 帧率始终可选（分辨率已移至「字体与间距」区域，用于预览比例联动）
        self.combo_fps.config(state="readonly")
        enabled = self.var_export_video.get()
        self.chk_trans.config(state="normal" if enabled else "disabled")
        # 根据「透明背景」开关，切换「透明格式 / 视频体积」两组控件的显示
        self._layout_export_options()
        try:
            self.update_preview()
        except Exception:
            pass

    def on_transparent_toggle(self):
        # 勾选/取消透明背景时，切换显示「透明格式」或「视频体积 + 实色背景」
        self._layout_export_options()
        try:
            self.update_preview()
        except Exception:
            pass

    def _layout_export_options(self):
        enabled = self.var_export_video.get()
        transparent = self.var_transparent.get()

        # 先全部移除，再按当前状态放置，保证布局干净
        for w in (self.lbl_fmt, self.combo_fmt, self.lbl_size,
                  self.combo_size, self.lbl_bg_btn_text, self.btn_bg_color):
            w.grid_remove()

        if not enabled:
            return

        if transparent:
            # 透明输出：仅显示「透明格式」下拉
            self.lbl_fmt.grid(row=3, column=0, sticky="w", pady=5)
            self.combo_fmt.grid(row=3, column=1, columnspan=3, sticky="w", padx=5)
            self.combo_fmt.config(state="readonly")
        else:
            # 实色输出：显示「视频体积」下拉 + 实色背景颜色
            self.lbl_size.grid(row=3, column=0, sticky="w", pady=5)
            self.combo_size.grid(row=3, column=1, columnspan=3, sticky="w", padx=5)
            self.combo_size.config(state="readonly")
            self.lbl_bg_btn_text.grid(row=4, column=0, sticky="w", pady=5)
            self.btn_bg_color.grid(row=4, column=1, sticky="w", padx=5)
            self.btn_bg_color.config(state="normal")

    def start_thread(self):
        threading.Thread(target=self.start_conversion, daemon=True).start()

    def start_conversion(self):
        srt_path = self.entry_srt.get()
        if not srt_path or not os.path.exists(srt_path):
            messagebox.showerror("错误", "请先选择有效的 SRT 字幕文件！")
            return

        font_name = self.combo_font.get()
        if not font_name:
            messagebox.showerror("错误", "请选择一个合法的字体！")
            return

        self.btn_convert.config(text="⏳ 正在处理中，请稍候...", state="disabled")

        fs_hl = int(self.scale_fs_hl.get())
        fs_norm = int(self.scale_fs_norm.get())
        row_gap = int(self.scale_gap.get())
        hl_color_ass = hex_to_ass_color(self.hl_color)
        normal_color_ass = hex_to_ass_color(self.normal_color)
        
        res_str = self.combo_res.get().split(" ")[0]
        width, height = map(int, res_str.split("x"))
        fps = int(self.combo_fps.get())

        ass_path = os.path.splitext(srt_path)[0] + ".ass"

        try:
            duration = core_converter(srt_path, ass_path, font_name, fs_hl, fs_norm, row_gap, hl_color_ass, normal_color_ass, width, height)
            success_msg = f"🎉 特效字幕生成成功！\n文件保存在:\n{ass_path}"

            if self.var_export_video.get():
                dir_name = os.path.dirname(srt_path)
                ass_basename = os.path.basename(ass_path)

                # 统一构造背景滤镜、编码器与输出路径
                if self.var_transparent.get():
                    # 透明输出（保留 alpha 通道，拖入剪映即透明）——三种格式按所选
                    fmt = self.combo_fmt.get()
                    bg_filter = f"color=c=black@0:s={width}x{height}:r={fps}:d={duration}"
                    if "QuickTime RLE" in fmt:
                        # QuickTime RLE（qtrle）：8bit alpha，无损，体积中等
                        video_ext = ".mov"
                        vcodec = "qtrle"
                        pix_fmt = "argb"
                        codec_extra = []
                    elif "VP9" in fmt:
                        # WebM 必须为 VP9 编码 + WebM 封装；带透明通道必须用 yuva420p
                        video_ext = ".webm"
                        vcodec = "libvpx-vp9"
                        pix_fmt = "yuva420p"
                        # -f webm 强制 WebM 封装；row-mt + cpu-used 多线程提速，体积几乎不变
                        codec_extra = ['-f', 'webm',
                                       '-b:v', '0', '-crf', '24', '-auto-alt-ref', '0',
                                       '-row-mt', '1', '-cpu-used', '4', '-deadline', 'good']
                    else:
                        # ProRes 4444：10/12bit alpha，标准格式、兼容最佳，体积最大
                        video_ext = ".mov"
                        vcodec = "prores_ks"
                        pix_fmt = "yuva444p10le"
                        codec_extra = ['-profile:v', '4444']
                    video_path = os.path.splitext(srt_path)[0] + video_ext
                    video_basename = os.path.basename(video_path)
                else:
                    # 非透明输出：导出为 MP4（背景为用户选择的纯色），按所选体积大小压缩
                    size = self.combo_size.get()
                    video_ext = ".mp4"
                    video_path = os.path.splitext(srt_path)[0] + video_ext
                    video_basename = os.path.basename(video_path)
                    ffmpeg_bg = self.bg_color.replace('#', '0x')
                    bg_filter = f"color=c={ffmpeg_bg}:s={width}x{height}:r={fps}:d={duration}"
                    vcodec = "libx264"
                    pix_fmt = "yuv420p"
                    crf = '18' if "高品质" in size else ('30' if "高压缩" in size else '23')
                    codec_extra = ['-crf', crf]

                # 构造最终 ffmpeg 命令（在工作目录使用相对文件名，避免路径转义问题）
                # 显式指定输出帧率 -r，确保导出与所选 FPS 一致、播放流畅
                cmd = [
                    get_ffmpeg_path(), '-y',
                    '-f', 'lavfi', '-i', bg_filter,
                    '-vf', f"format=rgba,lut=a=0,subtitles='{ass_basename}':alpha=1",
                    '-c:v', vcodec,
                    *codec_extra,
                    '-pix_fmt', pix_fmt,
                    '-r', str(fps),
                    video_basename
                ]

                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                process = subprocess.Popen(cmd, cwd=dir_name, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=startupinfo)
                stdout, stderr = process.communicate()

                if process.returncode != 0:
                    raise RuntimeError(f"FFmpeg 视频渲染失败。\n错误详情: {stderr.decode('utf-8', errors='ignore')}")

                if self.var_transparent.get():
                    if video_ext == ".webm":
                        success_msg += (f"\n\n🎬 视频导出成功（VP9 透明 .webm，体积最小）！\n视频保存在:\n{video_path}"
                                        f"\n\n💡 提示：文件已大幅压缩且带透明通道，播放流畅。"
                                        f"请拖入剪映（较新版本支持 webm）即为透明；"
                                        f"若你的剪映无法导入 webm，请改选 ProRes 4444 或 QuickTime RLE 输出 .mov。")
                    else:
                        success_msg += (f"\n\n🎬 视频导出成功（透明 .mov）！\n视频保存在:\n{video_path}"
                                        f"\n\n💡 提示：透明 .mov 在普通播放器中预览为黑底属正常，"
                                        f"请直接拖入剪映，画面透明且播放流畅。"
                                        f"若觉得文件太大，可改选 VP9 (WebM) 输出体积更小的视频。")
                else:
                    success_msg += f"\n\n🎬 视频导出成功！\n视频保存在:\n{video_path}"

            messagebox.showinfo("成功", success_msg)

        except FileNotFoundError:
            messagebox.showerror("错误", "系统未检测到 FFmpeg，请先安装 FFmpeg 并将其添加至系统环境变量。")
        except Exception as e:
            messagebox.showerror("失败", f"发生错误:\n{str(e)}")
        finally:
            self.btn_convert.config(text="🚀 一 键 生 成 A S S 字 幕 / 视 频", state="normal")

if __name__ == "__main__":
    root = tk.Tk()
    app = AppMusicLyricsApp(root)
    root.mainloop()