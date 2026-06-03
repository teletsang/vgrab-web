#!/usr/bin/env python3
"""
vgrab CLI — 供 Agent/终端直接调用的命令行工具

用法:
    vgrab download <url> [--audio] [--proxy socks5://...]
    vgrab transcribe <video_path>
    vgrab analyze <video_path> [--mode summary|visual|tutorial|creative]
    vgrab status
"""
import argparse
import json
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://127.0.0.1:9999"


def _get(path):
    """GET 请求"""
    url = BASE_URL + path
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(path, data):
    """POST 请求"""
    url = BASE_URL + path
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _wait_task(poll_path, status_key="status", active_statuses=None, interval=2):
    """轮询等待任务完成"""
    if active_statuses is None:
        active_statuses = ["queued", "downloading", "analyzing", "transcribing", "recording", "organizing"]

    while True:
        data = _get(poll_path)
        status = data.get(status_key, "")
        progress = data.get("progress", "")

        if progress:
            print(f"  [{status}] {progress}", flush=True)

        if status not in active_statuses:
            return data

        time.sleep(interval)


def cmd_download(args):
    """下载视频"""
    options = {}
    if args.audio:
        options["audio_only"] = True
    if args.proxy:
        options["proxy"] = args.proxy
    if args.output:
        options["output_dir"] = args.output

    result = _post("/api/download", {"url": args.url, "options": options})

    if "error" in result:
        print(f"错误: {result['error']}", file=sys.stderr)
        return 1

    task_id = result["task_id"]
    print(f"任务已创建: {task_id}")

    # 等待完成
    data = _wait_task(f"/api/task/{task_id}")

    if data.get("status") == "done":
        print(f"\n✓ 下载完成: {data.get('title', '')}")
        for f in data.get("files", []):
            print(f"  📄 {f['name']} ({_fmt_size(f.get('size', 0))})")
            print(f"     路径: {f.get('path', '')}")
        return 0
    else:
        print(f"\n✗ 下载失败: {data.get('progress', '未知错误')}", file=sys.stderr)
        return 1


def cmd_transcribe(args):
    """转录视频"""
    settings = {}
    result = _post("/api/transcribe", {"video_path": args.video_path, "settings": settings})

    if "error" in result:
        print(f"错误: {result['error']}", file=sys.stderr)
        return 1

    transcribe_id = result["transcribe_id"]
    print(f"转录任务: {transcribe_id}")

    data = _wait_task(f"/api/transcribe/{transcribe_id}",
                      active_statuses=["transcribing"])

    if data.get("status") == "done":
        print(f"\n✓ 转录完成\n")
        print(data.get("result", ""))
        return 0
    else:
        print(f"\n✗ 转录失败: {data.get('progress', '')}", file=sys.stderr)
        return 1


def cmd_analyze(args):
    """分析视频"""
    settings = {"mode": args.mode}
    result = _post("/api/analyze", {"video_path": args.video_path, "settings": settings})

    if "error" in result:
        print(f"错误: {result['error']}", file=sys.stderr)
        return 1

    analyze_id = result["analyze_id"]
    print(f"分析任务: {analyze_id} (模式: {args.mode})")

    data = _wait_task(f"/api/analyze/{analyze_id}",
                      active_statuses=["analyzing"], interval=3)

    if data.get("status") == "done":
        print(f"\n✓ 分析完成\n")
        print(data.get("result", ""))
        return 0
    else:
        print(f"\n✗ 分析失败: {data.get('progress', '')}", file=sys.stderr)
        return 1


def cmd_record(args):
    """录制直播"""
    settings = {"title": args.title or "直播录制"}
    if args.duration:
        settings["max_duration"] = int(args.duration) * 60

    result = _post("/api/record", {"url": args.url, "settings": settings})

    if "error" in result:
        print(f"错误: {result['error']}", file=sys.stderr)
        return 1

    live_id = result["live_id"]
    print(f"录制任务: {live_id}")

    data = _wait_task(f"/api/record/{live_id}",
                      active_statuses=["recording", "stopping"], interval=5)

    if data.get("status") == "done":
        print(f"\n✓ 录制完成")
        print(f"  文件: {data.get('file_path', '')}")
        return 0
    else:
        print(f"\n✗ 录制失败: {data.get('progress', '')}", file=sys.stderr)
        return 1


def cmd_status(args):
    """检查后端状态"""
    try:
        data = _get("/api/status")
        print(f"扒扒侠 v{data.get('version', '?')}")
        print(f"状态: {'✓ 运行中' if data.get('ok') else '⚠ 缺少依赖'}")
        print(f"下载目录: {data.get('download_dir', '?')}")
        if data.get("missing_deps"):
            print(f"缺少: {', '.join(data['missing_deps'])}")
        return 0
    except (urllib.error.URLError, ConnectionRefusedError):
        print("✗ 后端未运行 (http://127.0.0.1:9999)", file=sys.stderr)
        print("  请先启动: python3 ~/vgrab-web/app.py", file=sys.stderr)
        return 1


def _fmt_size(b):
    if b < 1024:
        return f"{b} B"
    if b < 1048576:
        return f"{b/1024:.1f} KB"
    if b < 1073741824:
        return f"{b/1048576:.1f} MB"
    return f"{b/1073741824:.2f} GB"


def main():
    parser = argparse.ArgumentParser(
        prog="vgrab",
        description="扒扒侠 CLI — 视频下载/转录/分析"
    )
    sub = parser.add_subparsers(dest="command")

    # download
    p_dl = sub.add_parser("download", aliases=["dl", "d"], help="下载视频")
    p_dl.add_argument("url", help="视频链接")
    p_dl.add_argument("--audio", "-a", action="store_true", help="仅音频 (MP3)")
    p_dl.add_argument("--proxy", "-p", help="代理 (如 socks5://127.0.0.1:7890)")
    p_dl.add_argument("--output", "-o", help="输出目录")

    # transcribe
    p_tr = sub.add_parser("transcribe", aliases=["tr", "t"], help="转录音频/视频")
    p_tr.add_argument("video_path", help="视频/音频文件路径")

    # analyze
    p_az = sub.add_parser("analyze", aliases=["az", "a"], help="AI 分析视频")
    p_az.add_argument("video_path", help="视频文件路径")
    p_az.add_argument("--mode", "-m", default="summary",
                      choices=["summary", "visual", "tutorial", "creative"],
                      help="分析模式 (默认: summary)")

    # record
    p_rc = sub.add_parser("record", aliases=["rc", "r"], help="录制直播流")
    p_rc.add_argument("url", help="直播流地址")
    p_rc.add_argument("--title", "-t", help="录制标题")
    p_rc.add_argument("--duration", "-d", help="最大时长(分钟)")

    # status
    sub.add_parser("status", aliases=["s"], help="检查后端状态")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    cmd_map = {
        "download": cmd_download, "dl": cmd_download, "d": cmd_download,
        "transcribe": cmd_transcribe, "tr": cmd_transcribe, "t": cmd_transcribe,
        "analyze": cmd_analyze, "az": cmd_analyze, "a": cmd_analyze,
        "record": cmd_record, "rc": cmd_record, "r": cmd_record,
        "status": cmd_status, "s": cmd_status,
    }

    handler = cmd_map.get(args.command)
    if handler:
        sys.exit(handler(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
