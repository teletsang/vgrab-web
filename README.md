# vgrab-web — 智能视频抓取 Web 版

一个页面，粘贴链接就能下载视频。支持 1000+ 网站。

## 快速启动

```bash
# 安装依赖
pip install flask yt-dlp
brew install ffmpeg   # macOS
# apt install ffmpeg  # Linux

# 启动服务
python app.py

# 指定端口和下载目录
python app.py --port 9999 --output ~/Videos
```

启动后打开 `http://localhost:8888` 或同一网络下其他设备访问 `http://<本机IP>:8888`

## 功能

- ✅ 粘贴任意视频链接一键下载
- ✅ 支持 YouTube、B站、抖音、Twitter/X、Vimeo 等 1000+ 平台
- ✅ 仅音频模式（MP3）
- ✅ 自动下载字幕
- ✅ 代理支持（socks5/http）
- ✅ m3u8/rtmp 流自动用 ffmpeg 录制
- ✅ 实时进度条
- ✅ 下载完成后可直接在页面下载文件
- ✅ 多任务并行
- ✅ 暗色主题，移动端适配

## 部署到服务器

```bash
# 后台运行
nohup python app.py --port 8888 > vgrab.log 2>&1 &

# 或用 systemd (Linux)
# 创建 /etc/systemd/system/vgrab-web.service
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `VGRAB_DOWNLOAD_DIR` | 下载文件存放目录 | `~/Downloads/vgrab-web` |

## 系统要求

- Python 3.8+
- ffmpeg
- yt-dlp
- Flask
