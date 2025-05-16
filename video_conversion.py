# -*- coding: utf-8 -*-
"""
视频转换模块 - 提供与MoviePy兼容的视频转换功能
"""
import os
import subprocess
import tempfile
import json
import time
import traceback
from datetime import datetime
import locale
import sys
import shutil

# 设置控制台输出编码
if sys.platform == 'win32':
    # Windows平台设置控制台编码为UTF-8
    try:
        # 获取当前编码
        system_encoding = locale.getpreferredencoding()
        # 设置标准输出和标准错误的编码
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 常见视频编解码器映射表
VIDEO_CODEC_MAP = {
    # H.264
    'h264': 'libx264',
    'avc': 'libx264',
    'x264': 'libx264',
    # H.265/HEVC
    'h265': 'libx265',
    'hevc': 'libx265',
    'x265': 'libx265',
    # VP9
    'vp9': 'libvpx-vp9',
    # AV1
    'av1': 'libaom-av1',
    # 其他
    'mpeg4': 'mpeg4',
    'mpeg2video': 'mpeg2video',
    'vp8': 'libvpx',
    'theora': 'libtheora',
}

# 常见音频编解码器映射表
AUDIO_CODEC_MAP = {
    'aac': 'aac',
    'mp3': 'libmp3lame',
    'opus': 'libopus',
    'vorbis': 'libvorbis',
    'flac': 'flac',
    'pcm_s16le': 'pcm_s16le',  # WAV
}

class VideoConverter:
    """视频转换类，提供视频文件转换功能"""
    
    def __init__(self, ffmpeg_path=None, ffprobe_path=None, log_function=None):
        """
        初始化转换器
        
        Args:
            ffmpeg_path: ffmpeg可执行文件路径，如果为None将自动搜索
            ffprobe_path: ffprobe可执行文件路径，如果为None将自动搜索
            log_function: 日志记录回调函数
        """
        self.ffmpeg_path = ffmpeg_path or self._find_executable('ffmpeg')
        self.ffprobe_path = ffprobe_path or self._find_executable('ffprobe')
        self.log_function = log_function
        self._temp_files = []  # 临时文件列表，用于清理
    
    def log(self, message):
        """记录日志消息"""
        if self.log_function:
            self.log_function(message)
        else:
            print(message)
    
    def _find_executable(self, name):
        """查找可执行文件路径"""
        import platform
        try:
            if platform.system() == "Windows":
                result = subprocess.run(["where", name], 
                                      capture_output=True, 
                                      text=True, 
                                      encoding='utf-8')  # 明确指定UTF-8编码
            else:
                result = subprocess.run(["which", name], 
                                      capture_output=True, 
                                      text=True,
                                      encoding='utf-8')  # 明确指定UTF-8编码
                
            if result.returncode == 0:
                paths = result.stdout.strip().split('\n')
                if paths:
                    return paths[0]
        except Exception as e:
            self.log(f"查找 {name} 时出错: {e}")
        
        return None
    
    def cleanup(self):
        """清理临时文件"""
        for temp_file in self._temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
                    self.log(f"已删除临时文件: {temp_file}")
            except Exception as e:
                self.log(f"删除临时文件 {temp_file} 失败: {e}")
        
        self._temp_files = []
    
    def get_video_info(self, input_path):
        """
        获取视频文件信息
        
        Args:
            input_path: 输入视频文件路径
            
        Returns:
            dict: 包含视频信息的字典，如果失败则返回None
        """
        if not self.ffprobe_path:
            self.log("FFprobe不可用，无法获取视频信息")
            return None
        
        if not os.path.exists(input_path):
            self.log(f"文件不存在: {input_path}")
            return None
        
        try:
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                input_path
            ]
            
            # 明确指定UTF-8编码处理输出
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            if result.returncode != 0:
                self.log(f"FFprobe执行失败: {result.stderr}")
                return None
            
            return json.loads(result.stdout)
        
        except Exception as e:
            self.log(f"获取视频信息时出错: {e}")
            return None
    
    def identify_problematic_streams(self, input_path):
        """
        识别可能导致MoviePy不兼容的视频流
        
        Args:
            input_path: 输入视频文件路径
            
        Returns:
            dict: 包含问题流的字典 {'video_issues': [...], 'audio_issues': [...]}
        """
        result = {"video_issues": [], "audio_issues": []}
        
        if not self.ffprobe_path:
            return result
        
        info = self.get_video_info(input_path)
        if not info:
            return result
        
        # 检查视频流
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                codec_name = stream.get("codec_name", "").lower()
                
                # 检查可能导致问题的编解码器
                if codec_name in ["hevc", "h265", "av1", "vp9"]:
                    result["video_issues"].append(
                        f"视频使用 {codec_name.upper()} 编码，可能不被MoviePy兼容"
                    )
                
                # 检查像素格式
                pix_fmt = stream.get("pix_fmt", "").lower()
                if pix_fmt and pix_fmt not in ["yuv420p", "yuvj420p", "rgb24", "bgr24"]:
                    result["video_issues"].append(
                        f"视频使用 {pix_fmt} 像素格式，可能不被MoviePy兼容"
                    )
                
                # 检查色彩空间
                color_space = stream.get("color_space", "").lower()
                if color_space and color_space not in ["bt709", "bt601", "bt470bg", "smpte170m"]:
                    result["video_issues"].append(
                        f"视频使用 {color_space} 色彩空间，可能不被MoviePy兼容"
                    )
            
            elif stream.get("codec_type") == "audio":
                codec_name = stream.get("codec_name", "").lower()
                
                # 检查可能导致问题的音频编解码器
                if codec_name not in ["aac", "mp3", "pcm_s16le"]:
                    result["audio_issues"].append(
                        f"音频使用 {codec_name} 编码，可能不被MoviePy兼容"
                    )
        
        return result
    
    def convert_video(self, input_path, output_path=None, options=None, delete_original=False):
        """
        转换视频为MoviePy兼容的格式
        
        Args:
            input_path: 输入视频文件路径
            output_path: 输出视频文件路径，如果为None则自动生成
            options: 转换选项字典
                - video_codec: 视频编解码器 (默认: 'libx264')
                - audio_codec: 音频编解码器 (默认: 'aac')
                - quality: 'low', 'medium', 'high' (默认: 'medium')
                - keep_audio: 是否保留音频 (默认: True)
                - resize: 调整大小 (格式: 'WIDTHxHEIGHT')
            delete_original: 转换成功后是否删除原始文件 (默认: False)
                
        Returns:
            (success, output_path, message): 成功标志、输出文件路径和消息
        """
        if not self.ffmpeg_path:
            return False, None, "FFmpeg不可用，无法转换视频"
        
        if not os.path.exists(input_path):
            return False, None, f"输入文件不存在: {input_path}"
        
        # 默认选项
        default_options = {
            "video_codec": "libx264",
            "audio_codec": "aac",
            "quality": "medium",
            "keep_audio": True,
            "resize": None,
            "format": "mp4"
        }
        
        # 合并选项
        opts = default_options.copy()
        if options:
            opts.update(options)
        
        # 如果未指定输出路径，则生成一个
        if not output_path:
            dirname = os.path.dirname(input_path)
            basename = os.path.basename(input_path)
            name, _ = os.path.splitext(basename)
            output_path = os.path.join(
                dirname, 
                f"{name}_converted_{int(time.time())}.{opts['format']}"
            )
        
        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                self.log(f"创建输出目录: {output_dir}")
            except Exception as e:
                return False, None, f"无法创建输出目录: {str(e)}"
        
        # 质量预设（添加色彩空间转换参数）
        quality_presets = {
            "high": {
                "libx264": ["-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"],
                "libx265": ["-preset", "slow", "-crf", "22", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"],
                "libvpx-vp9": ["-b:v", "2M", "-crf", "24", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"],
                "audio_bitrate": "192k"
            },
            "medium": {
                "libx264": ["-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"],
                "libx265": ["-preset", "medium", "-crf", "28", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"],
                "libvpx-vp9": ["-b:v", "1M", "-crf", "30", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"],
                "audio_bitrate": "128k"
            },
            "low": {
                "libx264": ["-preset", "ultrafast", "-crf", "28", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"],
                "libx265": ["-preset", "ultrafast", "-crf", "35", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"],
                "libvpx-vp9": ["-b:v", "500k", "-crf", "35", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"],
                "audio_bitrate": "96k"
            }
        }
        
        # 选择质量
        quality = opts["quality"]
        if quality not in quality_presets:
            quality = "medium"
        
        # 获取视频编解码器设置
        video_codec = opts["video_codec"]
        video_params = quality_presets[quality].get(
            video_codec, 
            quality_presets[quality]["libx264"]  # 默认使用libx264设置
        )
        
        # 音频比特率
        audio_bitrate = quality_presets[quality]["audio_bitrate"]
        
        # 构建基本命令
        cmd = [
            self.ffmpeg_path,
            "-y",  # 覆盖输出文件
            "-i", input_path,  # 输入文件
            "-c:v", video_codec,  # 视频编解码器
            *video_params,  # 视频质量参数（包含色彩空间参数）
        ]
        
        # 添加音频相关命令
        if opts["keep_audio"]:
            cmd.extend([
                "-c:a", opts["audio_codec"],  # 音频编解码器
                "-b:a", audio_bitrate,  # 音频比特率
                "-ar", "44100",  # 音频采样率
            ])
        else:
            cmd.extend(["-an"])  # 不包含音频
        
        # 调整大小（如果指定）
        if opts["resize"]:
            cmd.extend(["-vf", f"scale={opts['resize']}"])
        
        # 添加输出文件路径
        cmd.append(output_path)
        
        self.log(f"开始转换视频: {os.path.basename(input_path)}")
        self.log(f"输出文件: {output_path}")
        self.log(f"转换参数: 视频编码={video_codec}, 质量={quality}")
        self.log(f"色彩空间将被转换为BT.709")
        
        # 执行转换
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                encoding='utf-8'  # 明确指定UTF-8编码
            )
            
            # 读取输出并更新日志
            while True:
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    self.log(output.strip())
            
            # 获取返回码
            return_code = process.poll()
            
            if return_code != 0:
                return False, None, f"FFmpeg转换失败，返回代码: {return_code}"
            
            # 检查输出文件是否创建成功
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                return False, None, "转换失败: 输出文件未创建或为空"
            
            # 如果转换成功并且设置了删除原始文件选项
            if delete_original:
                try:
                    os.remove(input_path)
                    self.log(f"已删除原始文件: {input_path}")
                except Exception as e:
                    self.log(f"删除原始文件时出错: {str(e)}")
                    # 即使删除失败，我们仍然返回转换成功
            
            return True, output_path, "视频转换成功"
            
        except Exception as e:
            self.log(f"转换过程发生错误: {str(e)}")
            traceback.print_exc()
            return False, None, f"转换错误: {str(e)}"
    
    def repair_video(self, input_path, output_path=None, delete_original=False):
        """
        修复视频使其与MoviePy兼容
        
        Args:
            input_path: 输入视频文件路径
            output_path: 输出视频文件路径，如果为None则自动生成
            delete_original: 修复成功后是否删除原始文件 (默认: False)
            
        Returns:
            (success, output_path, message): 成功标志、输出文件路径和消息
        """
        # 分析视频问题
        issues = self.identify_problematic_streams(input_path)
        
        # 根据问题选择最佳修复策略
        options = {
            "video_codec": "libx264",
            "audio_codec": "aac",
            "quality": "medium",
            "keep_audio": True
        }
        
        if issues["video_issues"]:
            self.log(f"检测到视频问题: {', '.join(issues['video_issues'])}")
            # 默认策略足够处理大多数视频问题
        
        if issues["audio_issues"]:
            self.log(f"检测到音频问题: {', '.join(issues['audio_issues'])}")
            if "音频使用" in str(issues["audio_issues"]):
                # 如果是编解码器问题，使用AAC
                options["audio_codec"] = "aac"
        
        # 执行转换
        return self.convert_video(input_path, output_path, options, delete_original)
    
    def create_preview(self, input_path, duration=10, output_path=None, delete_original=False):
        """
        创建视频预览片段
        
        Args:
            input_path: 输入视频文件路径
            duration: 预览片段长度（秒）
            output_path: 输出预览文件路径
            delete_original: 预览创建成功后是否删除原始文件 (默认: False)
            
        Returns:
            (success, output_path, message): 成功标志、输出文件路径和消息
        """
        if not self.ffmpeg_path:
            return False, None, "FFmpeg不可用，无法创建预览"
        
        if not os.path.exists(input_path):
            return False, None, f"输入文件不存在: {input_path}"
        
        # 获取视频信息
        info = self.get_video_info(input_path)
        if not info:
            return False, None, "无法获取视频信息"
        
        # 确定预览开始时间（跳过前5秒，除非视频较短）
        video_duration = 0
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                if "duration" in stream:
                    try:
                        video_duration = float(stream["duration"])
                    except (ValueError, TypeError):
                        pass
        
        if not video_duration:
            # 尝试从格式信息获取
            try:
                video_duration = float(info.get("format", {}).get("duration", 0))
            except (ValueError, TypeError):
                pass
        
        if video_duration <= 0:
            return False, None, "无法确定视频时长"
        
        # 如果视频较短，调整预览时长
        if video_duration < duration:
            duration = max(1, video_duration - 0.5)  # 至少保留0.5秒的余量
        
        # 开始时间：如果视频足够长，跳过前5秒
        start_time = min(5, max(0, video_duration / 4)) if video_duration > duration + 10 else 0
        
        # 如果未指定输出路径，则生成一个
        if not output_path:
            dirname = os.path.dirname(input_path)
            basename = os.path.basename(input_path)
            name, ext = os.path.splitext(basename)
            output_path = os.path.join(dirname, f"{name}_preview{ext}")
        
        # 构建命令（添加色彩空间转换参数）
        cmd = [
            self.ffmpeg_path,
            "-y",  # 覆盖输出文件
            "-ss", str(start_time),  # 起始时间
            "-i", input_path,  # 输入文件
            "-t", str(duration),  # 持续时间
            "-c:v", "libx264",  # 视频编解码器
            "-preset", "ultrafast",  # 使用最快的预设
            "-crf", "23",  # 中等质量
            "-pix_fmt", "yuv420p",  # 像素格式
            "-color_primaries", "bt709",  # 色彩空间参数
            "-color_trc", "bt709",       # 色彩空间参数
            "-colorspace", "bt709",      # 色彩空间参数
            "-c:a", "aac",  # 音频编解码器
            "-b:a", "128k",  # 音频比特率
            output_path  # 输出文件
        ]
        
        self.log(f"创建预览: {os.path.basename(input_path)}")
        self.log(f"预览位置: {start_time}s 到 {start_time + duration}s")
        
        try:
            # 明确指定UTF-8编码
            process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            
            if process.returncode != 0:
                self.log(f"创建预览失败: {process.stderr}")
                return False, None, f"创建预览失败: {process.stderr}"
            
            # 检查输出文件是否创建成功
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                return False, None, "创建预览失败: 输出文件未创建或为空"
            
            # 如果创建预览成功并且设置了删除原始文件选项
            if delete_original:
                try:
                    os.remove(input_path)
                    self.log(f"已删除原始文件: {input_path}")
                except Exception as e:
                    self.log(f"删除原始文件时出错: {str(e)}")
                    # 即使删除失败，我们仍然返回创建预览成功
            
            return True, output_path, "预览创建成功"
            
        except Exception as e:
            self.log(f"创建预览过程发生错误: {str(e)}")
            return False, None, f"创建预览错误: {str(e)}"
    
    def extract_frame(self, input_path, time_pos=None, output_path=None, delete_original=False):
        """
        从视频中提取单帧图像
        
        Args:
            input_path: 输入视频文件路径
            time_pos: 提取帧的时间位置（秒），如果为None则使用视频中间位置
            output_path: 输出图像文件路径
            delete_original: 提取成功后是否删除原始文件 (默认: False)
            
        Returns:
            (success, output_path, message): 成功标志、输出文件路径和消息
        """
        if not self.ffmpeg_path:
            return False, None, "FFmpeg不可用，无法提取帧"
        
        if not os.path.exists(input_path):
            return False, None, f"输入文件不存在: {input_path}"
        
        # 获取视频信息
        info = self.get_video_info(input_path)
        if not info:
            return False, None, "无法获取视频信息"
        
        # 确定提取帧的时间位置
        video_duration = 0
        for stream in info.get("streams", []):
            if stream.get("codec_type") == "video":
                if "duration" in stream:
                    try:
                        video_duration = float(stream["duration"])
                    except (ValueError, TypeError):
                        pass
        
        if not video_duration:
            # 尝试从格式信息获取
            try:
                video_duration = float(info.get("format", {}).get("duration", 0))
            except (ValueError, TypeError):
                pass
        
        if video_duration <= 0:
            return False, None, "无法确定视频时长"
        
        # 如果未指定时间位置，使用视频中间位置
        if time_pos is None:
            time_pos = video_duration / 2
        
        # 确保时间位置在视频范围内
        time_pos = max(0, min(time_pos, video_duration - 0.1))
        
        # 如果未指定输出路径，则生成一个
        if not output_path:
            dirname = os.path.dirname(input_path)
            basename = os.path.basename(input_path)
            name, _ = os.path.splitext(basename)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(dirname, f"{name}_frame_{timestamp}.jpg")
        
        # 构建命令
        cmd = [
            self.ffmpeg_path,
            "-y",  # 覆盖输出文件
            "-ss", str(time_pos),  # 时间位置
            "-i", input_path,  # 输入文件
            "-vframes", "1",  # 提取1帧
            "-q:v", "2",  # 高质量
            output_path  # 输出文件
        ]
        
        self.log(f"从视频提取帧: {os.path.basename(input_path)}")
        self.log(f"时间位置: {time_pos:.2f}s")
        
        try:
            # 明确指定UTF-8编码
            process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            
            if process.returncode != 0:
                self.log(f"提取帧失败: {process.stderr}")
                return False, None, f"提取帧失败: {process.stderr}"
            
            # 检查输出文件是否创建成功
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                return False, None, "提取帧失败: 输出文件未创建或为空"
            
            # 如果提取成功并且设置了删除原始文件选项
            if delete_original:
                try:
                    os.remove(input_path)
                    self.log(f"已删除原始文件: {input_path}")
                except Exception as e:
                    self.log(f"删除原始文件时出错: {str(e)}")
                    # 即使删除失败，我们仍然返回提取帧成功
            
            return True, output_path, "帧提取成功"
            
        except Exception as e:
            self.log(f"提取帧过程发生错误: {str(e)}")
            return False, None, f"提取帧错误: {str(e)}"