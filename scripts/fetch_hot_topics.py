#!/usr/bin/env python3
"""
考公面试热点自动抓取脚本
从官方媒体 RSS/页面抓取最新时政热点，生成 hot_topics.json
每天由 GitHub Actions 自动运行
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from html.parser import HTMLParser

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("需要安装 requests 和 beautifulsoup4")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
JSON_PATH = os.path.join(PROJECT_DIR, "hot_topics.json")

# 官方媒体 RSS 源
RSS_SOURCES = [
    {
        "name": "人民日报",
        "url": "http://www.people.com.cn/rss/politics.xml",
        "cat": "政治"
    },
    {
        "name": "新华社",
        "url": "http://www.xinhuanet.com/politics/xhll.xml",
        "cat": "时政"
    },
    {
        "name": "央视新闻",
        "url": "https://news.cctv.com/2019/07/ga498/yeyaoframedata/rss.xml",
        "cat": "社会"
    },
    {
        "name": "求是",
        "url": "http://www.qstheory.cn/v7/rss/wzjj.xml",
        "cat": "理论"
    },
]

CATEGORY_KEYWORDS = {
    "政治": ["政治", "习近平", "党中央", "国务院", "中央", "党建", "从严治党", "反腐"],
    "经济": ["经济", "GDP", "财政", "金融", "产业", "贸易", "消费", "投资", "就业", "社保"],
    "社会": ["民生", "教育", "医疗", "住房", "养老", "交通", "环保", "生态", "碳中和"],
    "科技": ["科技", "人工智能", "AI", "芯片", "5G", "航天", "卫星", "量子", "数字"],
    "文化": ["文化", "旅游", "非遗", "博物馆", "传统", "文艺"],
    "法治": ["法治", "法律", "司法", "法院", "检察", "公安"],
    "国际": ["国际", "外交", "中美", "一带一路", "金砖", "G20", "联合国"],
}

CATEGORY_MAP = {
    "政治": "政治",
    "经济": "经济",
    "社会": "社会民生",
    "科技": "科技创新",
    "文化": "文化教育",
    "法治": "法治建设",
    "国际": "国际关系",
}


def classify_topic(title):
    """根据标题关键词自动分类"""
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in title:
                return CATEGORY_MAP.get(cat, "社会民生")
    return "社会民生"


class RSSParser(HTMLParser):
    """简易 RSS XML 解析器"""

    def __init__(self):
        super().__init__()
        self.items = []
        self.current = {}
        self.in_item = False
        self.tag = ""

    def handle_starttag(self, tag, attrs):
        if tag == "item":
            self.in_item = True
            self.current = {}
        if self.in_item:
            self.tag = tag

    def handle_endtag(self, tag):
        if tag == "item" and self.current:
            title = self.current.get("title", "")
            link = self.current.get("link", "")
            pub_date = self.current.get("pubDate", "")
            desc = self.current.get("description", "")
            if title and link:
                self.items.append({
                    "title": self._clean(title),
                    "url": self._clean(link),
                    "date": self._parse_date(pub_date),
                    "desc": self._clean(desc)[:200],
                })
            self.in_item = False
        self.tag = ""

    def handle_data(self, data):
        if self.in_item and self.tag:
            data = data.strip()
            if data:
                self.current[self.tag] = (
                    self.current.get(self.tag, "") + data
                )

    def _clean(self, text):
        """去除 HTML 标签和 CDATA"""
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"<!\[CDATA\[|\]\]>", "", text)
        text = re.sub(r"&[a-z]+;", " ", text)
        return text.strip()

    def _parse_date(self, date_str):
        """尝试解析日期"""
        if not date_str:
            return ""
        try:
            for fmt in [
                "%a, %d %b %Y %H:%M:%S %z",
                "%Y-%m-%d",
                "%Y-%m-%dT%H:%M:%S",
            ]:
                try:
                    dt = datetime.strptime(date_str.strip(), fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
        except Exception:
            pass
        # 尝试提取日期
        m = re.search(r"(\d{4}-\d{2}-\d{2})", date_str)
        if m:
            return m.group(1)
        return ""


def fetch_rss(source):
    """抓取单个 RSS 源"""
    try:
        resp = requests.get(source["url"], timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (compatible; HotTopicsBot/1.0)"
        })
        resp.encoding = resp.apparent_encoding or "utf-8"
        parser = RSSParser()
        parser.feed(resp.text)
        # 只取最近 7 天的
        cutoff = datetime.now() - timedelta(days=7)
        recent = []
        for item in parser.items:
            if item["date"]:
                try:
                    item_date = datetime.strptime(item["date"], "%Y-%m-%d")
                    if item_date >= cutoff:
                        recent.append(item)
                except ValueError:
                    recent.append(item)
            else:
                recent.append(item)
        return recent[:5]  # 每个源最多取 5 条
    except Exception as e:
        print(f"  [{source['name']}] 抓取失败: {e}")
        return []


def generate_article(title, cat):
    """基于标题生成简要摘要"""
    templates = [
        f"「{title}」近日引发广泛关注。{cat}领域的这一动态，反映了当前社会发展的重要趋势，值得考生深入了解和思考。",
        f"关于「{title}」的最新报道，展现了{cat}工作的新进展。这一事件对理解当前形势和政策走向具有重要参考价值。",
    ]
    idx = hash(title) % len(templates)
    return templates[idx]


def generate_commentary(title, cat):
    """生成面试评论分析"""
    return {
        "analysis": f"本题考查对「{title}」的理解和分析能力。答题时应从现象出发，分析背后的原因和影响，结合国家政策和社会实际，提出自己的见解。",
        "framework": "① 现象概述 → ② 原因分析 → ③ 影响论述 → ④ 对策建议 → ⑤ 总结升华",
        "keywords": [title[:6], cat, "政策", "民生", "发展"],
    }


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始抓取热点...")

    all_items = []
    for source in RSS_SOURCES:
        print(f"抓取: {source['name']} ({source['url']})")
        items = fetch_rss(source)
        for item in items:
            item["source_name"] = source["name"]
        all_items.extend(items)
        print(f"  获取 {len(items)} 条")

    if len(all_items) < 5:
        print(f"警告: 只获取到 {len(all_items)} 条热点，数据可能不完整")
        # 保留现有数据
        if os.path.exists(JSON_PATH):
            print("保留现有热点数据不覆盖")
            return

    # 去重，按标题相似度
    seen = set()

    def _simplify(t):
        return re.sub(r"\s+", "", t)[:10]

    unique = []
    for item in all_items:
        key = _simplify(item["title"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    # 按日期排序，取最新的 16 条
    unique.sort(key=lambda x: x.get("date", "0000-00-00"), reverse=True)
    unique = unique[:16]

    # 转换为 hot_topics 格式
    topics = []
    for i, item in enumerate(unique):
        cat = classify_topic(item["title"])
        article = generate_article(item["title"], cat)
        commentary = generate_commentary(item["title"], cat)

        topic = {
            "t": item["title"],
            "cat": cat,
            "src": f"{item['source_name']} · {item.get('date', '近日')}",
            "article": article,
            "commentary": commentary,
        }
        topics.append(topic)
        print(f"  [{i+1}] {cat} | {item['title'][:30]}...")

    data = {
        "lastUpdate": datetime.now().strftime("%Y-%m-%d"),
        "source": "官方媒体自动抓取 (人民日报/新华社/央视/求是)",
        "count": len(topics),
        "topics": topics,
    }

    # 备份
    if os.path.exists(JSON_PATH):
        backup = JSON_PATH + ".bak"
        import shutil
        shutil.copy2(JSON_PATH, backup)
        print(f"已备份: {backup}")

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"已保存 {len(topics)} 条热点到 {JSON_PATH}")


if __name__ == "__main__":
    main()
