# -*- coding: utf-8 -*-
"""
视频检测与修复工具 - 主程序
可用于检测视频文件是否可被MoviePy正确处理，并提供修复功能
"""
import os
import sys
import tkinter as tk
from tkinter import ttk

# 导入自定义模块
from video_detector import VideoDetectorApp

def main():
    """主程序入口"""
    # 创建主窗口
    root = tk.Tk()
    root.title("视频检测与修复工具")
    
    # 设置窗口图标（如果有）
    try:
        if os.path.exists("assets/app_icon.ico"):
            root.iconbitmap("assets/app_icon.ico")
    except Exception:
        pass
    
    # 设置主题样式
    style = ttk.Style()
    try:
        style.theme_use('clam')  # 尝试使用现代主题
    except tk.TclError:
        pass
    
    # 初始化应用
    app = VideoDetectorApp(root)
    
    # 启动主循环
    root.mainloop()

if __name__ == "__main__":
    main()