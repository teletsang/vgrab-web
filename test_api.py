#!/usr/bin/env python3
"""
扒扒侠 API 集成测试
用法: python3 test_api.py
确保后端在 127.0.0.1:9999 运行
"""
import json
import urllib.request
import sys
import time

BASE = "http://127.0.0.1:9999"
PASS = 0
FAIL = 0


def test(name, method, path, body=None, expect_status=200):
    global PASS, FAIL
    url = BASE + path
    headers = {"Content-Type": "application/json"}
    
    try:
        if body:
            data = json.dumps(body).encode()
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
        else:
            req = urllib.request.Request(url, method=method)
        
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            result = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        status = e.code
        result = {}
    except Exception as e:
        print(f"  ❌ {name} — 连接失败: {e}")
        FAIL += 1
        return None

    if status == expect_status:
        print(f"  ✅ {name} — {status}")
        PASS += 1
        return result
    else:
        print(f"  ❌ {name} — 期望 {expect_status}, 实际 {status}")
        FAIL += 1
        return result


def main():
    global PASS, FAIL
    print("\n🦐 扒扒侠 API 集成测试\n" + "=" * 40)

    # ===== 基础 =====
    print("\n[基础]")
    test("GET /api/status", "GET", "/api/status")

    # ===== 下载 =====
    print("\n[下载]")
    r = test("POST /api/download", "POST", "/api/download",
             body={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "options": {}})
    
    if r and "task_id" in r:
        task_id = r["task_id"]
        # 轮询路径验证（SwiftUI 调的是这个）
        test(f"GET /api/task/<id> (轮询)", "GET", f"/api/task/{task_id}")
    else:
        print("  ⚠️  跳过轮询测试（未获取 task_id）")

    test("GET /api/tasks (任务列表)", "GET", "/api/tasks")

    # 验证错误路径（SwiftUI 之前的 bug）
    test("GET /api/download/<id> (错误路径应404)", "GET", "/api/download/fake_id", expect_status=404)

    # ===== 分析 =====
    print("\n[分析]")
    r = test("POST /api/analyze (无效路径返回400)", "POST", "/api/analyze",
             body={"video_path": "/tmp/nonexistent.mp4", "settings": {"mode": "summary"}}, expect_status=400)
    
    if r and "analyze_id" in r:
        aid = r["analyze_id"]
        test(f"GET /api/analyze/<id> (轮询)", "GET", f"/api/analyze/{aid}")

    test("GET /api/analyze/tasks", "GET", "/api/analyze/tasks")

    # ===== 转录 =====
    print("\n[转录]")
    r = test("POST /api/transcribe (无效路径返回400)", "POST", "/api/transcribe",
             body={"video_path": "/tmp/nonexistent.mp4", "settings": {}}, expect_status=400)
    
    if r and "transcribe_id" in r:
        tid = r["transcribe_id"]
        test(f"GET /api/transcribe/<id> (轮询)", "GET", f"/api/transcribe/{tid}")

    # ===== 录制 =====
    print("\n[录制]")
    r = test("POST /api/record (无效URL返回400)", "POST", "/api/record",
             body={"stream_url": "http://fake.stream/live.m3u8", "settings": {}}, expect_status=400)
    
    if r and "live_id" in r:
        lid = r["live_id"]
        test(f"GET /api/record/<id> (轮询)", "GET", f"/api/record/{lid}")

    test("GET /api/record/tasks", "GET", "/api/record/tasks")

    # ===== 文件浏览 =====
    print("\n[文件浏览]")
    test("GET /api/browse (根目录)", "GET", "/api/browse?path=/tmp")

    # ===== Wiki 检索 =====
    print("\n[Wiki 模块]")
    try:
        sys.path.insert(0, "/Users/mbp2026/.openclaw/workspace/openclaw-knowledge-vault/scripts/vgrab-web")
        from core.wiki import search_wiki, _load_index, _index
        _load_index()
        if len(_index) > 0:
            results = search_wiki(["cyberpunk", "赛博朋克"])
            if results:
                print(f"  ✅ Wiki 检索 — 索引 {len(_index)} 条, 搜到 {len(results)} 条: {results[0]['title']}")
                PASS += 1
            else:
                print(f"  ❌ Wiki 检索 — 索引 {len(_index)} 条但搜索无结果")
                FAIL += 1
        else:
            print(f"  ❌ Wiki 索引为空")
            FAIL += 1
    except Exception as e:
        print(f"  ❌ Wiki 模块异常: {e}")
        FAIL += 1

    # ===== LLM 连通性 =====
    print("\n[LLM 连通性]")
    try:
        from core.llm import call_llm
        r = call_llm([{"role": "user", "content": "回复OK"}],
                     {"llm_url": "http://127.0.0.1:8080", "model": "gemma-4", "api_key": "", "max_tokens": 10, "temperature": 0},
                     timeout=30)
        if r:
            print(f"  ✅ 本地 LLM — 响应: {r[:30]}")
            PASS += 1
        else:
            print(f"  ❌ 本地 LLM 无响应")
            FAIL += 1
    except Exception as e:
        print(f"  ❌ 本地 LLM 失败: {e}")
        FAIL += 1

    # ===== 总结 =====
    print("\n" + "=" * 40)
    total = PASS + FAIL
    print(f"结果: {PASS}/{total} 通过, {FAIL}/{total} 失败")
    if FAIL > 0:
        print("⚠️  有失败项，请检查")
        sys.exit(1)
    else:
        print("🎉 全部通过")


if __name__ == "__main__":
    main()
