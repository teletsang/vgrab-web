#!/usr/bin/env python3
"""
vgrab-web — 重构版入口
下载和分析完全解耦，互不影响
"""
import re
import sys
from pathlib import Path

# 确保模块路径
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template, request, jsonify, send_from_directory
from core.config import DOWNLOAD_DIR, HOST, PORT, ALLOWED_ROOTS
from core.logger import get_logger
from core.validation import validate_download_request, validate_path_input, validate_organize_request, rate_limiter
from features.download import downloader
from features.analyze import analyzer
from features.transcribe import transcriber
from features.record import recorder
from features.organize import organizer

app = Flask(__name__, template_folder="templates", static_folder="static")
logger = get_logger("app")


# ============================================================
# 安全中间件
# ============================================================

@app.before_request
def security_checks():
    """CSRF 防护 + 限流"""
    if request.method in ('POST', 'PUT', 'DELETE'):
        # CSRF: 验证 Origin（精确匹配，防止 startswith 绕过）
        origin = request.headers.get('Origin', '').rstrip('/')
        referer = request.headers.get('Referer', '')
        check_value = origin or referer
        if check_value:
            from urllib.parse import urlparse
            parsed = urlparse(check_value)
            origin_host_port = f"{parsed.hostname}:{parsed.port}" if parsed.port else parsed.hostname
            allowed = {
                f'127.0.0.1:{PORT}', f'localhost:{PORT}', f'0.0.0.0:{PORT}',
                '127.0.0.1:9999', 'localhost:9999',
            }
            if origin_host_port not in allowed:
                return jsonify({"error": "请求来源不合法", "code": 403}), 403

        # 限流
        client_ip = request.remote_addr or "unknown"
        if not rate_limiter.allow(client_ip):
            return jsonify({"error": "请求过于频繁，请稍后再试", "code": 429}), 429


@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": str(e.description), "code": 400}), 400


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "资源不存在", "code": 404}), 404


@app.errorhandler(500)
def internal_error(e):
    logger.error("Internal server error", exc_info=True)
    return jsonify({"error": "服务器内部错误", "code": 500}), 500


def _is_path_allowed(p: Path) -> bool:
    """检查路径是否在允许的根目录下"""
    resolved = p.resolve()
    for root in ALLOWED_ROOTS:
        root_resolved = root.resolve()
        if resolved == root_resolved or root_resolved in resolved.parents:
            return True
    return False


# ============================================================
# 页面
# ============================================================

@app.route("/")
def index():
    return render_template("index.html")


# ============================================================
# 文件浏览 API
# ============================================================

@app.route("/api/browse")
def api_browse():
    """浏览目录，返回文件/文件夹列表（限制在白名单目录内）"""
    path = request.args.get("path", "").strip()
    if not path:
        path = str(DOWNLOAD_DIR)

    p = Path(path).expanduser().resolve()

    # 安全：检查路径是否在允许范围内
    if not _is_path_allowed(p):
        return jsonify({"error": "路径不在允许范围内", "code": 403}), 403

    if not p.exists() or not p.is_dir():
        return jsonify({"error": "目录不存在", "path": str(p)}), 400

    items = []
    try:
        # 父目录（同样检查白名单）
        if p.parent != p and _is_path_allowed(p.parent):
            items.append({"name": "..", "path": str(p.parent), "type": "dir"})

        for child in sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if child.name.startswith("."):
                continue
            if child.is_dir():
                items.append({"name": child.name + "/", "path": str(child), "type": "dir"})
            else:
                ext = child.suffix.lower()
                video_exts = ('.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.ts', '.m4a', '.mp3', '.wav')
                if ext in video_exts or ext in ('.txt', '.srt', '.vtt', '.md'):
                    size = child.stat().st_size
                    items.append({"name": child.name, "path": str(child), "type": "file", "size": size})
    except PermissionError:
        return jsonify({"error": "无权限访问"}), 403

    return jsonify({"path": str(p), "items": items})


# ============================================================
# 下载 API
# ============================================================

@app.route("/api/status")
def api_status():
    # 读取版本号
    version_file = Path(__file__).parent / "VERSION"
    version = version_file.read_text().strip() if version_file.exists() else "unknown"
    missing = downloader.check_deps()
    return jsonify({
        "ok": len(missing) == 0,
        "missing_deps": missing,
        "download_dir": str(DOWNLOAD_DIR),
        "version": version,
    })


@app.route("/api/download", methods=["POST"])
def api_download():
    data = request.get_json(silent=True)
    ok, err = validate_download_request(data)
    if not ok:
        return jsonify({"error": err, "code": 400}), 400
    url = data["url"].strip()
    task_id = downloader.create_task(url, data.get("options", {}))
    return jsonify({"task_id": task_id, "status": "queued"})


@app.route("/api/task/<task_id>")
def api_task(task_id):
    task = downloader.get_task(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(task)


@app.route("/api/tasks")
def api_tasks():
    return jsonify(downloader.get_all_tasks())


@app.route("/api/file/<task_id>/<path:filename>")
def api_file(task_id, filename):
    # 安全：校验 task_id 格式（UUID 前 8 位）
    if not re.match(r'^[a-f0-9\-]{8}$', task_id):
        return jsonify({"error": "无效任务ID", "code": 400}), 400
    # 安全：filename 只取文件名部分，阻止路径穿越
    import os
    safe_filename = os.path.basename(filename)
    if not safe_filename or safe_filename != filename:
        return jsonify({"error": "非法文件名", "code": 400}), 400
    file_dir = DOWNLOAD_DIR / task_id
    if not file_dir.exists():
        return "文件不存在", 404
    # 二次验证：最终路径必须在 file_dir 内
    target = (file_dir / safe_filename).resolve()
    if not str(target).startswith(str(file_dir.resolve())):
        return jsonify({"error": "路径非法", "code": 403}), 403
    # 如果有 download 参数则强制下载，否则允许浏览器预览
    as_attachment = 'download' in request.args
    return send_from_directory(str(file_dir), safe_filename, as_attachment=as_attachment)


# ============================================================
# 分析 API
# ============================================================

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求体必须是 JSON", "code": 400}), 400
    video_path = data.get("video_path", "").strip()
    settings = data.get("settings", {})

    ok, err = validate_path_input(video_path)
    if not ok:
        return jsonify({"error": err, "code": 400}), 400

    if not Path(video_path).exists():
        return jsonify({"error": "视频文件不存在", "code": 400}), 400

    analyze_id = analyzer.start_analyze(video_path, settings)
    return jsonify({"analyze_id": analyze_id, "status": "analyzing"})


@app.route("/api/analyze/<analyze_id>")
def api_analyze_status(analyze_id):
    task = analyzer.get_analyze_task(analyze_id)
    if not task:
        return jsonify({"error": "分析任务不存在"}), 404
    return jsonify(task)


@app.route("/api/analyze/tasks")
def api_analyze_tasks():
    return jsonify(analyzer.get_all_analyze_tasks())


# ============================================================
# 转录 API
# ============================================================

@app.route("/api/transcribe", methods=["POST"])
def api_transcribe():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求体必须是 JSON", "code": 400}), 400
    video_path = data.get("video_path", "").strip()
    settings = data.get("settings", {})

    ok, err = validate_path_input(video_path)
    if not ok:
        return jsonify({"error": err, "code": 400}), 400

    if not Path(video_path).exists():
        return jsonify({"error": "视频文件不存在", "code": 400}), 400

    transcribe_id = transcriber.start_transcribe(video_path, settings)
    return jsonify({"transcribe_id": transcribe_id, "status": "transcribing"})


@app.route("/api/transcribe/<transcribe_id>")
def api_transcribe_status(transcribe_id):
    task = transcriber.get_transcribe_task(transcribe_id)
    if not task:
        return jsonify({"error": "转录任务不存在"}), 404
    return jsonify(task)


# ============================================================
# 直播录制 API
# ============================================================

@app.route("/api/record", methods=["POST"])
def api_record():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "请求体必须是 JSON", "code": 400}), 400
    stream_url = data.get("url", "").strip()
    settings = data.get("settings", {})

    if not stream_url:
        return jsonify({"error": "需要直播流地址", "code": 400}), 400

    live_id = recorder.start_record(stream_url, settings)
    return jsonify({"live_id": live_id, "status": "recording"})


@app.route("/api/record/<live_id>")
def api_record_status(live_id):
    task = recorder.get_live_task(live_id)
    if not task:
        return jsonify({"error": "录制任务不存在"}), 404
    return jsonify(task)


@app.route("/api/record/<live_id>/stop", methods=["POST"])
def api_record_stop(live_id):
    ok = recorder.stop_record(live_id)
    if not ok:
        return jsonify({"error": "任务不存在或已停止"}), 404
    return jsonify({"status": "stopping"})


@app.route("/api/record/tasks")
def api_record_tasks():
    return jsonify(recorder.get_all_live_tasks())


# ============================================================
# 笔记整理 API
# ============================================================

@app.route("/api/organize", methods=["POST"])
def api_organize():
    data = request.get_json(silent=True)
    ok, err = validate_organize_request(data)
    if not ok:
        return jsonify({"error": err, "code": 400}), 400
    transcript = data["transcript"].strip()
    settings = data.get("settings", {})

    note_id = organizer.start_organize(transcript, settings)
    return jsonify({"note_id": note_id, "status": "organizing"})


@app.route("/api/organize/<note_id>")
def api_organize_status(note_id):
    task = organizer.get_note_task(note_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(task)


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="vgrab-web")
    parser.add_argument("--host", default=HOST)
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--production", action="store_true", help="使用 waitress WSGI 服务器")
    args = parser.parse_args()

    print(f"\n🦐 vgrab-web | http://127.0.0.1:{args.port}\n")

    if args.production:
        try:
            from waitress import serve
            logger.info(f"Production mode (waitress) on {args.host}:{args.port}")
            serve(app, host=args.host, port=args.port, threads=4)
        except ImportError:
            logger.warning("waitress 未安装，回退到 Flask 开发服务器")
            print("⚠️ waitress 未安装 (pip install waitress)，使用 Flask 开发服务器")
            app.run(host=args.host, port=args.port, debug=False)
    else:
        app.run(host=args.host, port=args.port, debug=False)
