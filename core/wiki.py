# core/wiki.py — 知识库检索模块
"""
从 vault/wiki/ 加载所有 .md 文件的 frontmatter，
建立关键词索引（title + aliases），支持模糊匹配。
"""
import os
import re
from pathlib import Path
from typing import Optional

# wiki 根目录（从项目根目录出发）
_project_root = Path(__file__).parent.parent  # vgrab-web/
_repo_root = _project_root.parent.parent  # openclaw-knowledge-vault/
WIKI_ROOT = _repo_root / "vault" / "wiki"

# 缓存：启动时加载一次
_index: list[dict] = []
_loaded = False


def _parse_frontmatter(filepath: Path) -> Optional[dict]:
    """解析 YAML frontmatter，只取需要的字段"""
    try:
        text = filepath.read_text(encoding="utf-8")
    except Exception:
        return None

    if not text.startswith("---"):
        return None

    end = text.find("---", 3)
    if end == -1:
        return None

    fm_text = text[3:end]
    
    # 简单解析，不引入 pyyaml 依赖
    entry = {
        "path": str(filepath),
        "type": "",
        "title": "",
        "aliases": [],
        "related_styles": [],
        "keywords": set(),
    }

    for line in fm_text.split("\n"):
        line = line.strip()
        if line.startswith("title:"):
            entry["title"] = line.split(":", 1)[1].strip().strip('"\'')
        elif line.startswith("type:"):
            entry["type"] = line.split(":", 1)[1].strip()
        elif line.startswith("- ") and "aliases" in fm_text[:fm_text.find(line)].split("\n")[-2]:
            # 解析 aliases 列表项
            pass

    # 用正则提取 aliases
    aliases_match = re.search(r'aliases:\s*\[([^\]]*)\]', fm_text)
    if aliases_match:
        aliases_raw = aliases_match.group(1)
        entry["aliases"] = [a.strip().strip('"\'') for a in aliases_raw.split(",") if a.strip()]

    # 构建关键词集合（小写用于匹配）
    entry["keywords"].add(entry["title"].lower())
    for a in entry["aliases"]:
        entry["keywords"].add(a.lower())
    # 文件名也作为关键词
    stem = filepath.stem.replace("-", " ").replace("_", " ")
    entry["keywords"].add(stem.lower())

    # 读取内容摘要（frontmatter 后的前 2000 字符）
    body = text[end+3:].strip()
    entry["summary"] = body[:2000]

    return entry


def _load_index():
    """扫描 wiki 目录，构建索引"""
    global _index, _loaded
    if _loaded:
        return

    if not WIKI_ROOT.exists():
        _loaded = True
        return

    for md_file in WIKI_ROOT.rglob("*.md"):
        # 跳过 index.md 和 log.md
        if md_file.name in ("index.md", "log.md"):
            continue
        entry = _parse_frontmatter(md_file)
        if entry and entry["title"]:
            _index.append(entry)

    _loaded = True


def search_wiki(keywords: list[str], max_results: int = 3) -> list[dict]:
    """
    根据关键词列表搜索 wiki，返回匹配的条目。
    
    Args:
        keywords: 要搜索的关键词列表
        max_results: 最多返回条目数
    
    Returns:
        匹配的条目列表，每个包含 title, type, path, summary
    """
    _load_index()

    if not _index or not keywords:
        return []

    # 计算每个条目的匹配得分
    scored = []
    search_terms = [k.lower().strip() for k in keywords if k.strip()]

    for entry in _index:
        score = 0
        for term in search_terms:
            # 精确匹配 title/alias
            if term in entry["keywords"]:
                score += 10
            # 部分匹配
            else:
                for kw in entry["keywords"]:
                    if term in kw or kw in term:
                        score += 5
                        break
                    # 中文关键词匹配
                    if len(term) >= 2 and term in entry.get("summary", "")[:500]:
                        score += 3
                        break

        if score > 0:
            scored.append((score, entry))

    # 按得分排序，取 top N
    scored.sort(key=lambda x: x[0], reverse=True)

    results = []
    for score, entry in scored[:max_results]:
        results.append({
            "title": entry["title"],
            "type": entry["type"],
            "path": entry["path"],
            "summary": entry["summary"][:1500],  # 限制长度
            "score": score,
        })

    return results


def format_wiki_context(results: list[dict]) -> str:
    """把搜索结果格式化为可塞入 prompt 的文本"""
    if not results:
        return ""

    parts = ["\n---\n## 知识库参考资料\n"]
    for r in results:
        parts.append(f"### {r['title']} ({r['type']})\n")
        # 取摘要的核心部分（跳过标题行）
        summary_lines = r["summary"].split("\n")
        # 跳过重复标题
        content = "\n".join(line for line in summary_lines[:40] if not line.startswith("# "))
        parts.append(content.strip()[:1000])
        parts.append("\n")

    return "\n".join(parts)
