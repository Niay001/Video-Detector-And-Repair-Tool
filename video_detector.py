# -*- coding: utf-8 -*-
"""
视频检测器模块 - 用于检测视频文件与MoviePy的兼容性
使用基于规则的检测方法，支持递归处理子文件夹，支持删除原文件
"""
import os
import sys
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import threading
import queue
import subprocess
import json
import tempfile
import time
from datetime import timedelta
import traceback
import platform
import shutil
import locale

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

class VideoInfo:
    """存储视频文件信息的类"""
    
    STATUS_UNKNOWN = "未知"
    STATUS_OK = "正常"
    STATUS_ERROR = "错误"
    STATUS_FIXED = "已修复"
    STATUS_PROCESSING = "处理中"
    
    def __init__(self, filepath):
        self.filepath = filepath  # 文件路径
        self.filename = os.path.basename(filepath)  # 文件名
        self.filesize = os.path.getsize(filepath)  # 文件大小(字节)
        self.status = self.STATUS_UNKNOWN  # 状态
        self.width = None  # 宽度
        self.height = None  # 高度
        self.duration = None  # 时长(秒)
        self.fps = None  # 帧率
        self.codec = None  # 编码格式
        self.video_bitrate = None  # 视频比特率
        self.audio_codec = None  # 音频编码
        self.audio_bitrate = None  # 音频比特率
        self.error_message = None  # 错误信息
        self.fixed_path = None  # 修复后的文件路径
        self.fixed_time = None  # 修复时间
        self.conversion_params = None  # 转换参数
        self.pixel_format = None  # 像素格式
        self.color_space = None  # 色彩空间
        self.issues = []  # 视频问题列表
    
    def format_filesize(self):
        """格式化文件大小为易读格式"""
        size = self.filesize
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0 or unit == 'GB':
                break
            size /= 1024.0
        return f"{size:.2f} {unit}"
    
    def format_duration(self):
        """格式化时长为易读格式"""
        if self.duration is None:
            return "未知"
        
        hours, remainder = divmod(int(self.duration), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    def get_resolution_str(self):
        """获取分辨率字符串"""
        if self.width is None or self.height is None:
            return "未知"
        return f"{self.width}x{self.height}"
    
    def get_summary(self):
        """获取视频信息摘要"""
        status_color = {
            self.STATUS_OK: "green",
            self.STATUS_ERROR: "red",
            self.STATUS_FIXED: "blue",
            self.STATUS_UNKNOWN: "black",
            self.STATUS_PROCESSING: "orange"
        }
        
        return {
            "filename": self.filename,
            "status": self.status,
            "status_color": status_color.get(self.status, "black"),
            "size": self.format_filesize(),
            "resolution": self.get_resolution_str(),
            "duration": self.format_duration(),
            "codec": self.codec or "未知"
        }
    
    def get_details(self):
        """获取详细信息文本"""
        details = []
        details.append(f"文件名: {self.filename}")
        details.append(f"状态: {self.status}")
        details.append(f"文件大小: {self.format_filesize()}")
        details.append(f"路径: {self.filepath}")
        
        if self.width and self.height:
            details.append(f"分辨率: {self.width}x{self.height}")
        
        if self.duration is not None:
            details.append(f"时长: {self.format_duration()}")
        
        if self.fps:
            details.append(f"帧率: {self.fps} FPS")
        
        if self.codec:
            details.append(f"视频编码: {self.codec}")
        
        if self.pixel_format:
            details.append(f"像素格式: {self.pixel_format}")
        
        if self.color_space:
            details.append(f"色彩空间: {self.color_space}")
        
        if self.video_bitrate:
            details.append(f"视频比特率: {self.video_bitrate}")
        
        if self.audio_codec:
            details.append(f"音频编码: {self.audio_codec}")
            
        if self.audio_bitrate:
            details.append(f"音频比特率: {self.audio_bitrate}")
        
        if self.issues:
            details.append("")
            details.append("检测到的问题:")
            for issue in self.issues:
                details.append(f"- {issue}")
        
        if self.error_message:
            details.append(f"\n错误信息: {self.error_message}")
        
        if self.fixed_path:
            details.append(f"\n修复文件: {os.path.basename(self.fixed_path)}")
            details.append(f"修复路径: {self.fixed_path}")
            
            if self.fixed_time:
                details.append(f"修复时间: {self.fixed_time}")
            
            if self.conversion_params:
                details.append(f"转换参数: {self.conversion_params}")
        
        return "\n".join(details)


class VideoDetector:
    """视频检测器类，用于检测和修复视频"""
    
    def __init__(self):
        """初始化视频检测器"""
        self.ffmpeg_path = self._find_executable('ffmpeg')
        self.ffprobe_path = self._find_executable('ffprobe')
        self.has_ffmpeg = self.ffmpeg_path is not None
        self.has_ffprobe = self.ffprobe_path is not None
        
        # 临时文件列表，用于清理
        self._temp_files = []
    
    def _find_executable(self, name):
        """查找系统中的可执行文件路径"""
        try:
            if platform.system() == "Windows":
                result = subprocess.run(["where", name], 
                                      capture_output=True, 
                                      text=True, 
                                      encoding='utf-8')
            else:
                result = subprocess.run(["which", name], 
                                      capture_output=True, 
                                      text=True,
                                      encoding='utf-8')
                
            if result.returncode == 0:
                paths = result.stdout.strip().split('\n')
                if paths:
                    return paths[0]
        except Exception:
            pass
        
        return None
    
    def cleanup(self):
        """清理临时文件"""
        for temp_file in self._temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception:
                pass
        self._temp_files = []
    
    def detect_video(self, video_path, callback=None):
        """
        检测视频文件，返回视频信息
        
        Args:
            video_path: 视频文件路径
            callback: 可选的回调函数，用于日志记录
            
        Returns:
            VideoInfo: 包含视频信息的对象
        """
        def log(msg):
            if callback:
                callback(msg)
            else:
                print(msg)
        
        if not os.path.exists(video_path):
            log(f"错误: 文件不存在 - {video_path}")
            return None
        
        info = VideoInfo(video_path)
        
        # 使用ffprobe获取视频信息
        if self.has_ffprobe:
            log(f"使用FFprobe检测视频: {os.path.basename(video_path)}")
            try:
                video_info = self._get_video_info(video_path)
                if video_info:
                    # 更新VideoInfo对象
                    for key, value in video_info.items():
                        if hasattr(info, key):
                            setattr(info, key, value)
                    
                    # 识别问题流
                    issues = self._identify_problematic_streams(video_path)
                    if issues:
                        info.issues = issues["video_issues"] + issues["audio_issues"]
                        
                        # 只要有问题就标记为错误
                        if issues["video_issues"] or issues["audio_issues"]:
                            info.status = VideoInfo.STATUS_ERROR
                            info.error_message = "检测到兼容性问题"
                        else:
                            info.status = VideoInfo.STATUS_OK
                    else:
                        info.status = VideoInfo.STATUS_OK
                    
                    log(f"检测完成: {info.get_resolution_str()}, {info.format_duration()}, 状态: {info.status}")
                    if info.issues:
                        for issue in info.issues:
                            log(f"- 问题: {issue}")
                else:
                    log(f"无法获取视频信息")
                    info.status = VideoInfo.STATUS_ERROR
                    info.error_message = "无法获取视频信息"
            except Exception as e:
                log(f"FFprobe检测失败: {str(e)}")
                info.status = VideoInfo.STATUS_ERROR
                info.error_message = f"检测失败: {str(e)}"
        else:
            # FFprobe不可用
            log("FFprobe不可用，无法检测视频兼容性")
            info.status = VideoInfo.STATUS_ERROR
            info.error_message = "检测工具不可用，请安装FFprobe"
        
        return info
    
    def _get_video_info(self, video_path):
        """使用ffprobe获取视频详细信息"""
        if not self.has_ffprobe:
            return None
        
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            if result.returncode != 0:
                raise Exception(f"FFprobe执行失败: {result.stderr}")
            
            data = json.loads(result.stdout)
            info = {}
            
            # 查找视频流和音频流
            video_stream = None
            audio_stream = None
            
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video" and not video_stream:
                    video_stream = stream
                elif stream.get("codec_type") == "audio" and not audio_stream:
                    audio_stream = stream
            
            # 提取视频信息
            if video_stream:
                info['width'] = int(video_stream.get("width", 0))
                info['height'] = int(video_stream.get("height", 0))
                info['codec'] = video_stream.get("codec_name")
                info['pixel_format'] = video_stream.get("pix_fmt")
                info['color_space'] = video_stream.get("color_space")
                
                # 处理帧率
                fps_str = video_stream.get("r_frame_rate", "")
                if fps_str and "/" in fps_str:
                    num, denom = map(int, fps_str.split("/"))
                    if denom != 0:
                        info['fps'] = round(num / denom, 2)
                
                # 视频比特率
                if "bit_rate" in video_stream:
                    try:
                        bitrate = int(video_stream["bit_rate"]) / 1000
                        info['video_bitrate'] = f"{bitrate:.0f} kbps"
                    except (ValueError, TypeError):
                        pass
            
            # 提取音频信息
            if audio_stream:
                info['audio_codec'] = audio_stream.get("codec_name")
                
                if "bit_rate" in audio_stream:
                    try:
                        bitrate = int(audio_stream["bit_rate"]) / 1000
                        info['audio_bitrate'] = f"{bitrate:.0f} kbps"
                    except (ValueError, TypeError):
                        pass
            
            # 提取格式信息
            format_info = data.get("format", {})
            if "duration" in format_info:
                try:
                    info['duration'] = float(format_info["duration"])
                except (ValueError, TypeError):
                    pass
            
            return info
            
        except json.JSONDecodeError as e:
            raise Exception(f"无法解析FFprobe输出: {e}")
        except Exception as e:
            raise Exception(f"获取视频信息时出错: {e}")
    
    def _identify_problematic_streams(self, input_path):
        """
        识别可能导致MoviePy不兼容的视频流
        
        Args:
            input_path: 输入视频文件路径
            
        Returns:
            dict: 包含问题流的字典 {'video_issues': [...], 'audio_issues': [...]}
        """
        result = {"video_issues": [], "audio_issues": []}
        
        if not self.has_ffprobe:
            return result
        
        try:
            video_info = self._get_video_info(input_path)
            if not video_info:
                return result
            
            # 获取完整的视频流信息，包括side data信息
            cmd = [
                self.ffprobe_path,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                "-show_data",
                input_path
            ]
            
            proc_result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
            if proc_result.returncode != 0:
                return result
            
            data = json.loads(proc_result.stdout)
            
            # 检查视频流
            for stream in data.get("streams", []):
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
                    
                    # 检查是否有side data，如Ambient Viewing Environment
                    side_data = stream.get("side_data_list", [])
                    for data_item in side_data:
                        if data_item.get("side_data_type") == "Ambient viewing environment":
                            result["video_issues"].append(
                                f"视频包含环境观看环境元数据，可能不被MoviePy兼容"
                            )
                
                elif stream.get("codec_type") == "audio":
                    codec_name = stream.get("codec_name", "").lower()
                    
                    # 检查可能导致问题的音频编解码器
                    if codec_name not in ["aac", "mp3", "pcm_s16le"]:
                        result["audio_issues"].append(
                            f"音频使用 {codec_name} 编码，可能不被MoviePy兼容"
                        )
            
            return result
        
        except Exception as e:
            # 错误处理：如果出现异常，记录错误但不中断检测
            print(f"识别问题流时出错: {e}")
            return result
    
    def fix_video(self, video_info, output_path=None, quality='medium', delete_original=False, callback=None):
        """
        修复不兼容的视频
        
        Args:
            video_info: VideoInfo对象
            output_path: 输出文件路径，如果为None，则使用原文件名（需要创建临时文件）
            quality: 转码质量，可选'low'、'medium'、'high'
            delete_original: 这个参数在不添加后缀的情况下被忽略，因为原文件会被替换
            callback: 可选的回调函数，用于日志记录
            
        Returns:
            (success, message): 成功标志和消息
        """
        def log(msg):
            if callback:
                callback(msg)
            else:
                print(msg)
        
        if not self.has_ffmpeg:
            return False, "未找到FFmpeg，无法修复视频"
        
        if video_info.status == VideoInfo.STATUS_OK:
            return True, "视频已兼容，无需修复"
        
        # 获取原文件路径和目录
        original_path = video_info.filepath
        dirname = os.path.dirname(original_path)
        basename = os.path.basename(original_path)
        
        # 创建临时输出文件路径
        temp_output_path = None
        if output_path is None:
            # 使用临时文件作为输出
            fd, temp_output_path = tempfile.mkstemp(suffix='.mp4', prefix='temp_fix_', dir=dirname)
            os.close(fd)  # 关闭文件描述符
            self._temp_files.append(temp_output_path)  # 添加到临时文件列表以便清理
            output_path = original_path  # 最终输出路径为原文件路径
        else:
            temp_output_path = output_path  # 如果指定了输出路径，直接使用
        
        # 确保输出目录存在
        output_dir = os.path.dirname(temp_output_path)
        if output_dir and not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                log(f"创建输出目录: {output_dir}")
            except Exception as e:
                return False, f"无法创建输出目录: {str(e)}"
        
        # 根据质量设置参数（使用更强力的方法移除侧数据）
        quality_settings = {
            'high': {
                'preset': 'slow',
                'crf': '18',
                'video_bitrate': '0'  # 0表示使用CRF而非固定比特率
            },
            'medium': {
                'preset': 'medium',
                'crf': '23',
                'video_bitrate': '0'
            },
            'low': {
                'preset': 'ultrafast',
                'crf': '28',
                'video_bitrate': '0'
            }
        }
        
        # 获取当前质量设置
        settings = quality_settings.get(quality, quality_settings['medium'])
        
        # 获取视频原始信息用于两阶段转换
        orig_info = self._get_video_info(original_path)
        width = orig_info.get('width', 1920) if orig_info else 1920
        height = orig_info.get('height', 1080) if orig_info else 1080
        fps = orig_info.get('fps', 30) if orig_info else 30
        
        # 创建raw中间文件路径
        raw_temp_path = None
        fd, raw_temp_path = tempfile.mkstemp(suffix='.yuv', prefix='raw_temp_', dir=dirname)
        os.close(fd)
        self._temp_files.append(raw_temp_path)
        
        # 第一阶段：解码到原始YUV，彻底移除所有元数据和侧数据
        log(f"阶段1: 将视频解码为原始YUV格式，清除所有元数据...")
        stage1_cmd = [
            self.ffmpeg_path,
            '-y',  # 覆盖输出文件
            '-i', original_path,  # 输入文件
            '-an',  # 不包含音频
            '-sn',  # 不包含字幕
            '-f', 'rawvideo',  # 原始视频格式
            '-pix_fmt', 'yuv420p',  # 像素格式
            raw_temp_path  # 输出到临时文件
        ]
        
        # 第二阶段：从原始YUV重新编码，仅保留原始音频
        log(f"阶段2: 从原始YUV重新编码视频，使用干净的容器...")
        stage2_cmd = [
            self.ffmpeg_path,
            '-y',  # 覆盖输出文件
            '-f', 'rawvideo',  # 输入格式为原始视频
            '-pix_fmt', 'yuv420p',  # 输入像素格式
            '-s', f'{width}x{height}',  # 视频尺寸
            '-r', str(fps),  # 帧率
            '-i', raw_temp_path,  # 原始视频输入
            '-i', original_path,  # 原始文件（仅用于提取音频）
            '-map', '0:v',  # 使用原始视频流
            '-map', '1:a?',  # 使用原始音频流（如果存在）
            '-c:v', 'libx264',  # 视频编码
            '-preset', settings['preset'],  # 编码预设
            '-crf', settings['crf'],  # 质量设置
            '-pix_fmt', 'yuv420p',  # 输出像素格式
            '-color_primaries', 'bt709',  # 色彩空间原色
            '-color_trc', 'bt709',  # 色彩空间传输特性
            '-colorspace', 'bt709',  # 色彩空间
            '-c:a', 'aac',  # 音频编码
            '-b:a', '128k',  # 音频比特率
            '-ar', '44100',  # 音频采样率
            '-movflags', '+faststart',  # 优化MP4结构
            temp_output_path  # 输出文件
        ]
        
        try:
            # 执行第一阶段：解码到原始YUV
            log(f"开始阶段1: 解码视频到原始格式...")
            
            process1 = subprocess.Popen(
                stage1_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                encoding='utf-8'
            )
            
            # 读取输出并更新日志
            while True:
                output = process1.stderr.readline()
                if output == '' and process1.poll() is not None:
                    break
                if output:
                    log(output.strip())
            
            # 获取返回码
            return_code1 = process1.poll()
            
            if return_code1 != 0:
                return False, f"阶段1解码失败，返回代码: {return_code1}"
            
            log(f"阶段1完成：成功解码到原始格式")
            
            # 执行第二阶段：重新编码
            log(f"开始阶段2: 重新编码视频...")
            
            process2 = subprocess.Popen(
                stage2_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                bufsize=1,
                encoding='utf-8'
            )
            
            # 读取输出并更新日志
            while True:
                output = process2.stderr.readline()
                if output == '' and process2.poll() is not None:
                    break
                if output:
                    log(output.strip())
            
            # 获取返回码
            return_code2 = process2.poll()
            
            if return_code2 != 0:
                return False, f"阶段2编码失败，返回代码: {return_code2}"
            
            # 检查输出文件是否创建成功
            if not os.path.exists(temp_output_path) or os.path.getsize(temp_output_path) == 0:
                return False, "转换失败: 输出文件未创建或为空"
            
            # 删除临时原始文件
            try:
                if os.path.exists(raw_temp_path):
                    os.remove(raw_temp_path)
                    log(f"已删除临时原始文件: {raw_temp_path}")
                    if raw_temp_path in self._temp_files:
                        self._temp_files.remove(raw_temp_path)
            except Exception as e:
                log(f"删除临时原始文件失败: {str(e)}")
            
            # 检查修复后的文件是否有兼容性问题
            log("验证修复后的文件...")
            new_issues = self._identify_problematic_streams(temp_output_path)
            if new_issues["video_issues"] or new_issues["audio_issues"]:
                log(f"警告: 修复后的文件仍存在兼容性问题:")
                for issue in new_issues["video_issues"] + new_issues["audio_issues"]:
                    log(f"- {issue}")
                # 但我们仍然继续，因为文件可能已经改善
            else:
                log("验证成功: 修复后的文件没有检测到兼容性问题")
            
            # 如果使用临时文件，现在替换原文件
            if temp_output_path != output_path:
                try:
                    # 原文件可能正在被其他程序使用，先尝试删除
                    if os.path.exists(original_path):
                        try:
                            os.remove(original_path)
                        except Exception as e:
                            log(f"无法删除原文件，尝试更改名称: {str(e)}")
                            # 如果无法删除，尝试重命名
                            backup_path = original_path + ".bak"
                            os.rename(original_path, backup_path)
                            log(f"已将原文件重命名为: {backup_path}")
                    
                    # 现在移动临时文件到目标位置
                    shutil.move(temp_output_path, output_path)
                    log(f"已将修复后的文件替换原文件: {output_path}")
                    
                    # 从临时文件列表中移除（已经移动了）
                    if temp_output_path in self._temp_files:
                        self._temp_files.remove(temp_output_path)
                except Exception as e:
                    return False, f"替换原文件时出错: {str(e)}"
            
            # 更新视频信息
            video_info.status = VideoInfo.STATUS_FIXED
            video_info.fixed_path = output_path
            video_info.fixed_time = time.strftime("%Y-%m-%d %H:%M:%S")
            video_info.conversion_params = f"质量: {quality}, 预设: {settings['preset']}, CRF: {settings['crf']}, 两阶段完全重编码"
            
            # 更新修复后的视频信息
            if self.has_ffprobe:
                try:
                    fixed_info = self._get_video_info(output_path)
                    if fixed_info and 'codec' in fixed_info:
                        log(f"修复后的编码: {fixed_info['codec']}")
                except Exception:
                    pass
            
            return True, f"视频修复成功: {os.path.basename(output_path)}"
            
        except Exception as e:
            log(f"转换过程发生错误: {str(e)}")
            traceback.print_exc()
            return False, f"转换错误: {str(e)}"
        finally:
            # 确保清理临时原始文件
            try:
                if os.path.exists(raw_temp_path):
                    os.remove(raw_temp_path)
                    if raw_temp_path in self._temp_files:
                        self._temp_files.remove(raw_temp_path)
            except Exception:
                pass


class VideoDetectorApp:
    """视频检测器应用类"""
    
    def __init__(self, master):
        """初始化应用"""
        self.master = master
        self.master.title("视频检测与修复工具")
        self.master.geometry("1000x700")
        self.master.minsize(800, 600)
        
        # 检测器实例
        self.detector = VideoDetector()
        
        # 添加删除原文件选项（放在这里，在_create_ui之前）- 对于直接替换模式，我们可以隐藏这个选项或改变其行为
        self.delete_original_var = tk.BooleanVar(value=False)
        self.keep_original_name_var = tk.BooleanVar(value=True)  # 新增：保持原文件名选项
        
        # 检查环境依赖
        self._check_dependencies()
        
        # 创建UI组件
        self._create_ui()
        
        # 初始化日志队列
        self.log_queue = queue.Queue()
        self.master.after(100, self._process_log_queue)
        
        # 存储检测结果
        self.video_info_list = []
        self.selected_video_index = -1
        
        # 记录日志
        self.log_message("视频检测工具已启动")
        self.log_message(f"FFmpeg {'可用' if self.detector.has_ffmpeg else '不可用'}")
        self.log_message(f"FFprobe {'可用' if self.detector.has_ffprobe else '不可用'}")
        self.log_message("使用基于规则的检测逻辑，检查视频编解码器、像素格式和色彩空间等参数")
        self.log_message("增强版修复引擎: 使用两阶段完全重编码方式，彻底清除侧数据")
    
    def _check_dependencies(self):
        """检查依赖"""
        missing = []
        
        if not self.detector.has_ffmpeg:
            missing.append("FFmpeg")
        
        if not self.detector.has_ffprobe:
            missing.append("FFprobe")
        
        if missing:
            msg = "检测到以下组件缺失，某些功能可能不可用:\n\n"
            msg += "\n".join(f"- {item}" for item in missing)
            msg += "\n\n推荐安装所有组件以获得完整功能。"
            messagebox.showwarning("缺少依赖", msg)
    
    def _create_ui(self):
        """创建用户界面"""
        self.style = ttk.Style()
        self._configure_styles()
        
        # 主框架
        main_frame = ttk.Frame(self.master, padding=(10, 5, 10, 0))
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 底部框架
        bottom_frame = ttk.Frame(self.master, padding=(10, 5, 10, 10))
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        # 顶部工具栏
        toolbar = ttk.Frame(main_frame)
        toolbar.pack(fill=tk.X, padx=5, pady=5)
        
        # 按钮栏
        btn_frame = ttk.Frame(toolbar)
        btn_frame.pack(side=tk.LEFT, fill=tk.X)
        
        # 添加按钮
        self.add_btn = ttk.Button(btn_frame, text="添加视频", command=self._browse_videos)
        self.add_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.folder_btn = ttk.Button(btn_frame, text="添加文件夹", command=self._browse_folder)
        self.folder_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.start_btn = ttk.Button(btn_frame, text="开始检测", command=self._start_detection)
        self.start_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.fix_btn = ttk.Button(btn_frame, text="修复所选", command=self._fix_selected)
        self.fix_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.fix_btn.config(state=tk.DISABLED)
        
        self.fix_all_btn = ttk.Button(btn_frame, text="修复全部", command=self._fix_all)
        self.fix_all_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.fix_all_btn.config(state=tk.DISABLED)
        
        self.clear_btn = ttk.Button(btn_frame, text="清空列表", command=self._clear_list)
        self.clear_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        # 选项框架
        options_frame = ttk.Frame(toolbar)
        options_frame.pack(side=tk.LEFT, padx=(10, 0))
        
        # 保持原文件名选项
        self.keep_name_checkbox = ttk.Checkbutton(
            options_frame, 
            text="保持原文件名（直接替换原文件）", 
            variable=self.keep_original_name_var
        )
        self.keep_name_checkbox.pack(side=tk.LEFT)
        self.keep_name_checkbox.state(['selected'])  # 默认选中
        
        # 删除原文件选项（当不选择保持原文件名时才有效）
        self.delete_checkbox = ttk.Checkbutton(
            options_frame, 
            text="修复后删除原文件", 
            variable=self.delete_original_var
        )
        self.delete_checkbox.pack(side=tk.LEFT, padx=(10, 0))
        
        # 监听保持原文件名变量，根据情况启用/禁用删除原文件选项
        self.keep_original_name_var.trace_add("write", self._update_delete_checkbox_state)
        self._update_delete_checkbox_state()  # 初始化时调用一次
        
        # 质量选择
        quality_frame = ttk.Frame(toolbar)
        quality_frame.pack(side=tk.RIGHT, padx=(0, 10))
        
        ttk.Label(quality_frame, text="转换质量:").pack(side=tk.LEFT)
        
        self.quality_var = tk.StringVar(value="medium")
        quality_combo = ttk.Combobox(quality_frame, textvariable=self.quality_var, 
                                   values=["low", "medium", "high"], width=8,
                                   state="readonly")
        quality_combo.pack(side=tk.LEFT, padx=(5, 0))
        
        # 内容区域 - 使用PanedWindow分割
        content = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        content.pack(fill=tk.BOTH, expand=True, pady=5)
        
        # 左侧列表
        left_frame = ttk.LabelFrame(content, text="文件列表")
        content.add(left_frame, weight=3)
        
        # 创建表格
        columns = ("filename", "status", "size", "resolution", "duration", "codec")
        self.tree = ttk.Treeview(left_frame, columns=columns, show="headings",
                               selectmode="browse")
        
        # 设置列
        self.tree.heading("filename", text="文件名")
        self.tree.heading("status", text="状态")
        self.tree.heading("size", text="大小")
        self.tree.heading("resolution", text="分辨率")
        self.tree.heading("duration", text="时长")
        self.tree.heading("codec", text="编码")
        
        # 设置列宽
        self.tree.column("filename", width=200)
        self.tree.column("status", width=60, anchor="center")
        self.tree.column("size", width=80, anchor="center")
        self.tree.column("resolution", width=100, anchor="center")
        self.tree.column("duration", width=80, anchor="center")
        self.tree.column("codec", width=80, anchor="center")
        
        # 滚动条
        tree_scroll = ttk.Scrollbar(left_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        
        # 放置表格和滚动条
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 绑定事件
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        
        # 右侧详情和日志
        right_pane = ttk.PanedWindow(content, orient=tk.VERTICAL)
        content.add(right_pane, weight=2)
        
        # 详情区域
        details_frame = ttk.LabelFrame(right_pane, text="详细信息")
        right_pane.add(details_frame, weight=1)
        
        self.details_text = tk.Text(details_frame, wrap=tk.WORD, width=40, height=10,
                                   font=("Consolas", 9))
        self.details_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        details_scroll = ttk.Scrollbar(details_frame, orient="vertical", 
                                     command=self.details_text.yview)
        self.details_text.configure(yscrollcommand=details_scroll.set)
        details_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=5)
        
        # 日志区域
        log_frame = ttk.LabelFrame(right_pane, text="操作日志")
        right_pane.add(log_frame, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, width=40, height=10,
                                                font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state=tk.DISABLED)
        
        # 状态栏
        status_frame = ttk.Frame(bottom_frame)
        status_frame.pack(fill=tk.X)
        
        self.status_var = tk.StringVar()
        self.status_var.set("就绪")
        status_label = ttk.Label(status_frame, textvariable=self.status_var)
        status_label.pack(side=tk.LEFT, padx=5)
        
        self.progress_var = tk.DoubleVar()
        self.progressbar = ttk.Progressbar(status_frame, variable=self.progress_var,
                                         length=200, mode="determinate")
        self.progressbar.pack(side=tk.RIGHT, padx=5)
    
    def _update_delete_checkbox_state(self, *args):
        """根据保持原文件名选项更新删除原文件选项的状态"""
        if self.keep_original_name_var.get():
            # 如果选择保持原文件名（直接替换原文件），则禁用删除原文件选项
            self.delete_checkbox.state(['disabled'])
            self.delete_original_var.set(False)
        else:
            # 如果不保持原文件名，则启用删除原文件选项
            self.delete_checkbox.state(['!disabled'])
    
    def _configure_styles(self):
        """配置样式"""
        # 配置常规按钮样式
        self.style.configure("TButton", padding=6)
        
        # 为状态列配置样式标签
        self.tree_tags_configured = False
    
    def _update_tree_tags(self):
        """更新树形视图标签样式"""
        if not self.tree_tags_configured:
            self.tree.tag_configure("ok", foreground="green")
            self.tree.tag_configure("error", foreground="red")
            self.tree.tag_configure("fixed", foreground="blue")
            self.tree.tag_configure("unknown", foreground="black")
            self.tree.tag_configure("processing", foreground="orange")
            self.tree_tags_configured = True
    
    def log_message(self, message):
        """添加消息到日志队列"""
        self.log_queue.put(message)
    
    def _process_log_queue(self):
        """处理日志队列中的消息"""
        try:
            while True:
                message = self.log_queue.get_nowait()
                
                self.log_text.config(state=tk.NORMAL)
                self.log_text.insert(tk.END, f"{message}\n")
                self.log_text.see(tk.END)
                self.log_text.config(state=tk.DISABLED)
        except queue.Empty:
            pass
        finally:
            self.master.after(100, self._process_log_queue)
    
    def _browse_videos(self):
        """浏览选择视频文件"""
        file_paths = filedialog.askopenfilenames(
            title="选择视频文件",
            filetypes=[
                ("视频文件", "*.mp4 *.avi *.mov *.mkv *.webm *.flv *.wmv"),
                ("所有文件", "*.*")
            ]
        )
        
        if not file_paths:
            return
        
        # 添加到文件列表
        for path in file_paths:
            self._add_to_file_list(path)
        
        self.log_message(f"已添加 {len(file_paths)} 个文件到列表")
        self.status_var.set(f"已添加 {len(file_paths)} 个文件")
    
    def _browse_folder(self):
        """浏览选择文件夹，支持递归查找子文件夹"""
        folder_path = filedialog.askdirectory(title="选择包含视频的文件夹")
        
        if not folder_path:
            return
        
        # 查找文件夹及其子文件夹中的视频文件
        video_extensions = (".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv", ".wmv")
        video_files = []
        
        # 选择是否搜索子文件夹
        include_subfolders = messagebox.askyesno(
            "子文件夹", 
            "是否包含子文件夹中的视频文件？"
        )
        
        if include_subfolders:
            # 递归搜索所有子文件夹
            for root, dirs, files in os.walk(folder_path):
                for file in files:
                    if file.lower().endswith(video_extensions):
                        video_files.append(os.path.join(root, file))
        else:
            # 只搜索当前文件夹
            for file in os.listdir(folder_path):
                filepath = os.path.join(folder_path, file)
                if os.path.isfile(filepath) and file.lower().endswith(video_extensions):
                    video_files.append(filepath)
        
        if not video_files:
            messagebox.showinfo("提示", f"在所选文件夹{' 及其子文件夹' if include_subfolders else ''}中未找到视频文件: {folder_path}")
            return
        
        # 确认是否添加
        confirm = messagebox.askyesno(
            "确认", 
            f"在文件夹{' 及其子文件夹' if include_subfolders else ''}中找到 {len(video_files)} 个视频文件。\n是否全部添加到列表？"
        )
        
        if not confirm:
            return
        
        # 添加到文件列表
        for path in video_files:
            self._add_to_file_list(path)
        
        self.log_message(f"已从文件夹{' 及其子文件夹' if include_subfolders else ''}添加 {len(video_files)} 个视频文件")
        self.status_var.set(f"已从文件夹添加 {len(video_files)} 个文件")
    
    def _add_to_file_list(self, file_path):
        """添加文件到列表"""
        # 检查是否已经在列表中
        for info in self.video_info_list:
            if info.filepath == file_path:
                self.log_message(f"文件已在列表中: {os.path.basename(file_path)}")
                return
        
        # 创建VideoInfo对象
        info = VideoInfo(file_path)
        self.video_info_list.append(info)
        
        # 添加到树形视图
        self._update_tree_tags()
        summary = info.get_summary()
        
        values = (
            summary["filename"],
            summary["status"],
            summary["size"],
            summary["resolution"],
            summary["duration"],
            summary["codec"]
        )
        
        item_id = self.tree.insert("", "end", values=values, tags=(summary["status"].lower(),))
        
        # 更新按钮状态
        self._update_buttons()
    
    def _update_file_list_item(self, index):
        """更新文件列表项"""
        if index < 0 or index >= len(self.video_info_list):
            return
        
        info = self.video_info_list[index]
        summary = info.get_summary()
        
        # 查找树形视图中对应的项
        for item_id in self.tree.get_children():
            if self.tree.item(item_id)["values"][0] == summary["filename"]:
                self.tree.item(
                    item_id, 
                    values=(
                        summary["filename"],
                        summary["status"],
                        summary["size"],
                        summary["resolution"],
                        summary["duration"],
                        summary["codec"]
                    ),
                    tags=(summary["status"].lower(),)
                )
                break
    
    def _on_tree_select(self, event):
        """树形视图选择事件处理"""
        selection = self.tree.selection()
        if not selection:
            return
        
        # 获取选中项的文件名
        item_id = selection[0]
        filename = self.tree.item(item_id)["values"][0]
        
        # 查找对应的VideoInfo
        for i, info in enumerate(self.video_info_list):
            if info.filename == filename:
                self.selected_video_index = i
                self._show_details(info)
                
                # 更新按钮状态
                self._update_buttons()
                break
    
    def _show_details(self, info):
        """显示详细信息"""
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete(1.0, tk.END)
        self.details_text.insert(tk.END, info.get_details())
        self.details_text.config(state=tk.DISABLED)
    
    def _clear_list(self):
        """清空文件列表"""
        if not self.video_info_list:
            return
        
        if len(self.video_info_list) > 0:
            confirm = messagebox.askyesno("确认", "确定要清空文件列表吗？")
            if not confirm:
                return
        
        self.video_info_list = []
        self.tree.delete(*self.tree.get_children())
        self.details_text.config(state=tk.NORMAL)
        self.details_text.delete(1.0, tk.END)
        self.details_text.config(state=tk.DISABLED)
        self.selected_video_index = -1
        
        self._update_buttons()
        self.log_message("已清空文件列表")
        self.status_var.set("就绪")
    
    def _update_buttons(self):
        """更新按钮状态"""
        has_files = len(self.video_info_list) > 0
        has_selection = self.selected_video_index >= 0
        has_errors = any(info.status == VideoInfo.STATUS_ERROR for info in self.video_info_list)
        
        # 开始检测按钮
        self.start_btn.config(state=tk.NORMAL if has_files else tk.DISABLED)
        
        # 修复按钮
        if has_selection and self.selected_video_index < len(self.video_info_list):
            selected_status = self.video_info_list[self.selected_video_index].status
            can_fix = selected_status == VideoInfo.STATUS_ERROR
            self.fix_btn.config(state=tk.NORMAL if can_fix else tk.DISABLED)
        else:
            self.fix_btn.config(state=tk.DISABLED)
        
        # 修复所有按钮
        self.fix_all_btn.config(state=tk.NORMAL if has_errors else tk.DISABLED)
        
        # 清空列表按钮
        self.clear_btn.config(state=tk.NORMAL if has_files else tk.DISABLED)
    
    def _start_detection(self):
        """开始检测过程"""
        if not self.video_info_list:
            messagebox.showinfo("提示", "没有文件可检测")
            return
        
        # 确认是否已检测过
        already_detected = [info for info in self.video_info_list 
                          if info.status != VideoInfo.STATUS_UNKNOWN]
        
        if already_detected:
            confirm = messagebox.askyesno(
                "确认", 
                f"列表中有 {len(already_detected)} 个文件已经检测过。\n是否重新检测所有文件？"
            )
            if not confirm:
                return
        
        # 禁用界面
        self._set_ui_state(False)
        
        # 更新进度条
        self.progress_var.set(0)
        
        # 启动检测线程
        detection_thread = threading.Thread(
            target=self._detection_worker,
            daemon=True
        )
        detection_thread.start()
    
    def _detection_worker(self):
        """检测工作线程"""
        try:
            total_files = len(self.video_info_list)
            self.log_message(f"开始检测 {total_files} 个视频文件")
            self.status_var.set(f"正在检测文件...")
            
            for i, info in enumerate(self.video_info_list):
                # 更新状态
                self.master.after(0, lambda: self.status_var.set(
                    f"正在检测 ({i+1}/{total_files}): {info.filename}"
                ))
                
                # 更新进度条
                progress = (i / total_files) * 100
                self.master.after(0, lambda p=progress: self.progress_var.set(p))
                
                # 设置状态为处理中
                info.status = VideoInfo.STATUS_PROCESSING
                self.master.after(0, lambda idx=i: self._update_file_list_item(idx))
                
                # 检测视频
                self.log_message(f"检测 ({i+1}/{total_files}): {info.filename}")
                
                detected_info = self.detector.detect_video(
                    info.filepath,
                    callback=self.log_message
                )
                
                if detected_info:
                    # 更新信息
                    self.video_info_list[i] = detected_info
                    
                    # 更新UI
                    self.master.after(0, lambda idx=i: self._update_file_list_item(idx))
                    
                    # 如果是当前选中项，更新详情
                    if i == self.selected_video_index:
                        self.master.after(0, lambda info=detected_info: self._show_details(info))
            
            # 检测完成，更新状态
            self.log_message("所有文件检测完成")
            self.master.after(0, lambda: self.status_var.set("检测完成"))
            self.master.after(0, lambda: self.progress_var.set(100))
            
            # 统计结果
            ok_count = sum(1 for info in self.video_info_list if info.status == VideoInfo.STATUS_OK)
            error_count = sum(1 for info in self.video_info_list if info.status == VideoInfo.STATUS_ERROR)
            
            self.log_message(f"检测结果: {total_files} 个文件中，{ok_count} 个正常，{error_count} 个错误")
            
            # 提示结果
            if error_count > 0:
                self.master.after(0, lambda: messagebox.showinfo(
                    "检测完成", 
                    f"检测完成！\n\n"
                    f"总计: {total_files} 个文件\n"
                    f"正常: {ok_count} 个\n"
                    f"错误: {error_count} 个\n\n"
                    f"可以选择错误文件并点击'修复所选'按钮进行修复。"
                ))
            else:
                self.master.after(0, lambda: messagebox.showinfo(
                    "检测完成", 
                    f"检测完成！所有 {total_files} 个文件均正常，可以被MoviePy正确处理。"
                ))
        
        except Exception as e:
            self.log_message(f"检测过程发生错误: {str(e)}")
            traceback.print_exc()
            
            self.master.after(0, lambda: messagebox.showerror(
                "错误",
                f"检测过程发生错误: {str(e)}\n请查看日志了解详情。"
            ))
        
        finally:
            # 恢复界面
            self.master.after(0, lambda: self._set_ui_state(True))
            self.master.after(0, self._update_buttons)
    
    def _fix_selected(self):
        """修复选中的视频"""
        if self.selected_video_index < 0 or self.selected_video_index >= len(self.video_info_list):
            return
        
        info = self.video_info_list[self.selected_video_index]
        
        if info.status != VideoInfo.STATUS_ERROR:
            messagebox.showinfo("提示", f"文件 '{info.filename}' 不需要修复")
            return
        
        # 根据保持原文件名选项确定输出路径和删除原文件设置
        keep_original_name = self.keep_original_name_var.get()
        delete_original = self.delete_original_var.get() and not keep_original_name
        
        if keep_original_name:
            # 直接替换原文件（使用原文件名）
            output_path = None  # 让修复函数自己处理临时文件和替换
        else:
            # 使用添加后缀的文件名
            dirname = os.path.dirname(info.filepath)
            basename = os.path.basename(info.filepath)
            name, ext = os.path.splitext(basename)
            output_path = os.path.join(dirname, f"{name}_fixed.mp4")
        
        # 获取质量设置
        quality = self.quality_var.get()
        
        # 确认修复
        message = f"是否修复文件 '{info.filename}'?\n\n"
        if keep_original_name:
            message += "将直接替换原文件 (保持原文件名)\n"
        else:
            message += f"输出文件将保存为新文件: {os.path.basename(output_path)}\n"
            if delete_original:
                message += "修复后将删除原文件\n"
        message += f"转换质量: {quality}\n"
        message += "注意: 修复将使用两阶段完全重编码方式，可能需要较长时间"
        
        confirm = messagebox.askyesno("确认", message)
        
        if not confirm:
            return
        
        # 禁用界面
        self._set_ui_state(False)
        
        # 启动修复线程
        fix_thread = threading.Thread(
            target=self._fix_worker,
            args=(self.selected_video_index, output_path, quality, delete_original),
            daemon=True
        )
        fix_thread.start()
    
    def _fix_all(self):
        """修复所有错误视频"""
        # 查找所有错误视频
        error_indices = [i for i, info in enumerate(self.video_info_list) 
                      if info.status == VideoInfo.STATUS_ERROR]
        
        if not error_indices:
            messagebox.showinfo("提示", "没有需要修复的错误视频")
            return
        
        # 根据保持原文件名选项确定删除原文件设置
        keep_original_name = self.keep_original_name_var.get()
        delete_original = self.delete_original_var.get() and not keep_original_name
        
        # 获取质量设置
        quality = self.quality_var.get()
        
        # 确认修复
        message = f"是否修复所有 {len(error_indices)} 个错误视频?\n\n"
        if keep_original_name:
            message += "将直接替换原文件 (保持原文件名)\n"
        else:
            message += f"输出文件将保存为新文件 (添加'_fixed'后缀)\n"
            if delete_original:
                message += "修复后将删除原文件\n"
        message += f"转换质量: {quality}\n"
        message += "注意: 修复将使用两阶段完全重编码方式，可能需要较长时间"
        
        confirm = messagebox.askyesno("确认", message)
        
        if not confirm:
            return
        
        # 禁用界面
        self._set_ui_state(False)
        
        # 启动批量修复线程
        fix_thread = threading.Thread(
            target=self._batch_fix_worker,
            args=(error_indices, quality, delete_original, keep_original_name),
            daemon=True
        )
        fix_thread.start()
    
    def _fix_worker(self, index, output_path, quality, delete_original):
        """修复工作线程"""
        try:
            if index < 0 or index >= len(self.video_info_list):
                return
            
            info = self.video_info_list[index]
            
            # 更新状态
            self.master.after(0, lambda: self.status_var.set(f"正在修复: {info.filename}"))
            self.log_message(f"开始修复: {info.filename}")
            
            # 设置状态为处理中
            info.status = VideoInfo.STATUS_PROCESSING
            self.master.after(0, lambda idx=index: self._update_file_list_item(idx))
            
            # 修复视频
            success, message = self.detector.fix_video(
                info,
                output_path=output_path,
                quality=quality,
                delete_original=delete_original,
                callback=self.log_message
            )
            
            if success:
                self.log_message(f"修复成功: {os.path.basename(output_path or info.filepath)}")
                
                # 更新UI
                self.master.after(0, lambda idx=index: self._update_file_list_item(idx))
                
                # 如果是当前选中项，更新详情
                if index == self.selected_video_index:
                    self.master.after(0, lambda info=info: self._show_details(info))
                
                # 提示成功
                if output_path:
                    success_msg = f"文件 '{info.filename}' 修复成功！\n\n" \
                                f"修复后的文件保存在:\n{output_path}"
                    if delete_original:
                        success_msg += "\n\n原文件已删除"
                else:
                    success_msg = f"文件 '{info.filename}' 修复成功！\n\n" \
                                  f"已直接替换原文件。"
                
                self.master.after(0, lambda: messagebox.showinfo("修复成功", success_msg))
            else:
                # 还原状态
                info.status = VideoInfo.STATUS_ERROR
                self.master.after(0, lambda idx=index: self._update_file_list_item(idx))
                
                self.log_message(f"修复失败: {message}")
                
                # 提示失败
                self.master.after(0, lambda: messagebox.showerror(
                    "修复失败", 
                    f"文件 '{info.filename}' 修复失败！\n\n"
                    f"错误信息: {message}\n\n"
                    f"请查看日志了解详情。"
                ))
        
        except Exception as e:
            self.log_message(f"修复过程发生错误: {str(e)}")
            traceback.print_exc()
            
            self.master.after(0, lambda: messagebox.showerror(
                "错误",
                f"修复过程发生错误: {str(e)}\n请查看日志了解详情。"
            ))
        
        finally:
            # 恢复界面
            self.master.after(0, lambda: self._set_ui_state(True))
            self.master.after(0, self._update_buttons)
            self.master.after(0, lambda: self.status_var.set("就绪"))
    
    def _batch_fix_worker(self, indices, quality, delete_original, keep_original_name=False):
        """批量修复工作线程"""
        try:
            total = len(indices)
            self.log_message(f"开始批量修复 {total} 个文件")
            self.master.after(0, lambda: self.status_var.set(f"批量修复: 0/{total}"))
            self.master.after(0, lambda: self.progress_var.set(0))
            
            success_count = 0
            fail_count = 0
            
            for i, index in enumerate(indices):
                if index < 0 or index >= len(self.video_info_list):
                    continue
                
                info = self.video_info_list[index]
                
                # 更新状态
                self.master.after(0, lambda i=i, total=total, name=info.filename: 
                               self.status_var.set(f"批量修复: {i+1}/{total} - {name}"))
                
                # 更新进度条
                progress = (i / total) * 100
                self.master.after(0, lambda p=progress: self.progress_var.set(p))
                
                self.log_message(f"修复 ({i+1}/{total}): {info.filename}")
                
                # 设置状态为处理中
                info.status = VideoInfo.STATUS_PROCESSING
                self.master.after(0, lambda idx=index: self._update_file_list_item(idx))
                
                # 根据保持原文件名选项确定输出路径
                if keep_original_name:
                    output_path = None  # 直接替换原文件
                else:
                    # 使用添加后缀的文件名
                    dirname = os.path.dirname(info.filepath)
                    basename = os.path.basename(info.filepath)
                    name, ext = os.path.splitext(basename)
                    output_path = os.path.join(dirname, f"{name}_fixed.mp4")
                
                # 修复视频
                success, message = self.detector.fix_video(
                    info,
                    output_path=output_path,
                    quality=quality,
                    delete_original=delete_original,
                    callback=self.log_message
                )
                
                if success:
                    self.log_message(f"  成功: {os.path.basename(output_path or info.filepath)}")
                    success_count += 1
                else:
                    # 还原状态
                    info.status = VideoInfo.STATUS_ERROR
                    self.log_message(f"  失败: {message}")
                    fail_count += 1
                
                # 更新UI
                self.master.after(0, lambda idx=index: self._update_file_list_item(idx))
            
            # 完成后更新状态
            self.log_message(f"批量修复完成: {success_count} 成功, {fail_count} 失败")
            self.master.after(0, lambda: self.status_var.set("批量修复完成"))
            self.master.after(0, lambda: self.progress_var.set(100))
            
            # 提示结果
            if keep_original_name:
                message = f"批量修复完成！\n\n" \
                        f"总计: {total} 个文件\n" \
                        f"成功: {success_count} 个\n" \
                        f"失败: {fail_count} 个\n\n" \
                        f"成功修复的文件已直接替换原文件。"
            else:
                message = f"批量修复完成！\n\n" \
                        f"总计: {total} 个文件\n" \
                        f"成功: {success_count} 个\n" \
                        f"失败: {fail_count} 个"
                if delete_original and success_count > 0:
                    message += f"\n\n已删除 {success_count} 个原文件"
                
            self.master.after(0, lambda: messagebox.showinfo("批量修复完成", message))
        
        except Exception as e:
            self.log_message(f"批量修复过程发生错误: {str(e)}")
            traceback.print_exc()
            
            self.master.after(0, lambda: messagebox.showerror(
                "错误",
                f"批量修复过程发生错误: {str(e)}\n请查看日志了解详情。"
            ))
        
        finally:
            # 恢复界面
            self.master.after(0, lambda: self._set_ui_state(True))
            self.master.after(0, self._update_buttons)
    
    def _set_ui_state(self, enabled):
        """设置UI状态"""
        state = tk.NORMAL if enabled else tk.DISABLED
        
        # 按钮
        self.add_btn.config(state=state)
        self.folder_btn.config(state=state)
        self.start_btn.config(state=state)
        self.clear_btn.config(state=state)
        self.delete_checkbox.config(state=state if not self.keep_original_name_var.get() else tk.DISABLED)
        self.keep_name_checkbox.config(state=state)
        
        # 修复按钮状态由_update_buttons控制
        if enabled:
            self._update_buttons()
        else:
            self.fix_btn.config(state=tk.DISABLED)
            self.fix_all_btn.config(state=tk.DISABLED)