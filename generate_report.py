#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日期货日报自动生成脚本
由 GitHub Actions 每日 9:30 (北京时间) 运行

功能：
  1. 下载当前 index.html 作为模板
  2. 更新页面日期为今日
  3. 从东方财富 + 华尔街见闻获取今日完整快讯
  4. 按板块分类整理，生成「今日要闻分析」
  5. 聚焦黄金相关新闻和金价事件
  6. 尝试获取期货价格（push2 API，可选）
  7. 注入新内容到页面，保留原有实时 JS 功能
"""

import json
import urllib.request
import urllib.parse
import re
import os
import ssl
import time
from datetime import datetime, timezone, timedelta

# ==================== 配置 ====================

TEMPLATE_URL = "https://huayubo-0701.github.io/futures-daily/"
OUTPUT_FILE = "index.html"
BEIJING_TZ = timezone(timedelta(hours=8))

# SSL 上下文（兼容性）
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

# 板块关键词（用于新闻分类）
SECTOR_KEYWORDS = {
    "能化板块": ["原油", "燃油", "PTA", "甲醇", "沥青", "纯碱", "塑料", "PVC",
                 "聚丙烯", "乙二醇", "苯乙烯", "橡胶", "纸浆", "石油", "OPEC",
                 "能化", "化工", "聚酯", "烯烃", "煤化工", "天然气", "LPG"],
    "有色金属": ["沪铜", "铜价", "铜矿", "沪铝", "铝价", "沪锌", "锌价",
                 "沪镍", "镍价", "沪锡", "锡价", "沪铅", "铅价",
                 "氧化铝", "有色", "基本金属", "LME", "铝土矿", "铜精矿"],
    "黑色系": ["螺纹", "钢材", "铁矿石", "铁矿", "焦煤", "焦炭", "热轧",
               "钢铁", "黑色", "玻璃", "铁水", "高炉", "电炉", "废钢",
               "钢厂", "螺纹钢", "铁矿石价格"],
    "农产品": ["豆粕", "豆油", "大豆", "棕榈油", "菜油", "菜粕", "玉米",
               "生猪", "猪肉", "鸡蛋", "棉花", "白糖", "苹果", "红枣",
               "花生", "菜籽", "农产", "养殖", "饲料", "油脂", "豆一"],
    "贵金属": ["黄金", "金价", "白银", "银价", "Au9999", "贵金属",
               "COMEX", "伦敦金", "金币", "金饰", "周大福", "老凤祥",
               "中国黄金", "金条", "黄金T+D", "央行购金", "黄金储备"],
}

# 期货主力合约（用于生成价格表，push2 API 可用时填充）
FUTURES_CONTRACTS = [
    # (secid, code, name, sector)
    ("113.CU0", "CU0", "沪铜", "有色金属"),
    ("113.AL0", "AL0", "沪铝", "有色金属"),
    ("113.ZN0", "ZN0", "沪锌", "有色金属"),
    ("113.NI0", "NI0", "沪镍", "有色金属"),
    ("113.SN0", "SN0", "沪锡", "有色金属"),
    ("113.PB0", "PB0", "沪铅", "有色金属"),
    ("113.AO0", "AO0", "氧化铝", "有色金属"),
    ("113.AU0", "AU0", "沪金", "贵金属"),
    ("113.AG0", "AG0", "沪银", "贵金属"),
    ("113.RB0", "RB0", "螺纹钢", "黑色系"),
    ("113.HC0", "HC0", "热轧卷板", "黑色系"),
    ("113.SS0", "SS0", "不锈钢", "黑色系"),
    ("114.I0", "I0", "铁矿石", "黑色系"),
    ("114.JM0", "JM0", "焦煤", "黑色系"),
    ("114.J0", "J0", "焦炭", "黑色系"),
    ("114.A0", "A0", "豆一", "农产品"),
    ("114.M0", "M0", "豆粕", "农产品"),
    ("114.Y0", "Y0", "豆油", "农产品"),
    ("114.P0", "P0", "棕榈油", "农产品"),
    ("114.C0", "C0", "玉米", "农产品"),
    ("114.LH0", "LH0", "生猪", "农产品"),
    ("114.JD0", "JD0", "鸡蛋", "农产品"),
    ("114.L0", "L0", "塑料", "能化板块"),
    ("114.V0", "V0", "PVC", "能化板块"),
    ("114.PP0", "PP0", "聚丙烯", "能化板块"),
    ("114.EG0", "EG0", "乙二醇", "能化板块"),
    ("115.TA0", "TA0", "PTA", "能化板块"),
    ("115.MA0", "MA0", "甲醇", "能化板块"),
    ("115.SA0", "SA0", "纯碱", "能化板块"),
    ("115.FG0", "FG0", "玻璃", "黑色系"),
    ("115.SR0", "SR0", "白糖", "农产品"),
    ("115.CF0", "CF0", "棉花", "农产品"),
    ("115.OI0", "OI0", "菜油", "农产品"),
    ("115.RM0", "RM0", "菜粕", "农产品"),
    ("117.SC0", "SC0", "原油", "能化板块"),
    ("117.FU0", "FU0", "燃料油", "能化板块"),
    ("117.LU0", "LU0", "低硫燃油", "能化板块"),
    ("117.NR0", "NR0", "20号胶", "能化板块"),
    ("117.EB0", "EB0", "苯乙烯", "能化板块"),
    ("117.BC0", "BC0", "国际铜", "有色金属"),
]

# ==================== 工具函数 ====================

def fetch_url(url, timeout=15):
    """获取 URL 内容"""
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://quote.eastmoney.com/'
    })
    return urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX).read().decode('utf-8')


def fetch_json(url, timeout=15):
    """获取并解析 JSON"""
    return json.loads(fetch_url(url, timeout))


def format_price(val):
    """格式化价格"""
    if val is None or val == 0 or val == '-':
        return '—'
    try:
        v = float(val)
        if v > 10000:
            return f"{v:,.0f}"
        elif v > 100:
            return f"{v:,.1f}"
        else:
            return f"{v:,.2f}"
    except (ValueError, TypeError):
        return str(val)


def format_change(val):
    """格式化涨跌幅，带颜色"""
    try:
        v = float(val)
    except (ValueError, TypeError):
        return '<span style="color:#888">—</span>'
    if v > 0:
        return f'<span style="color:#e74c3c;font-weight:600">+{v:.2f}%</span>'
    elif v < 0:
        return f'<span style="color:#27ae60;font-weight:600">{v:.2f}%</span>'
    else:
        return '<span style="color:#888">0.00%</span>'


# ==================== 数据获取 ====================

def fetch_eastmoney_news():
    """从东方财富获取快讯"""
    items = []
    try:
        ts = str(int(time.time() * 1000))
        url = f'https://newsapi.eastmoney.com/kuaixun/v1/getlist_101_ajaxResult_100_1_.html?_={ts}'
        text = fetch_url(url)
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            for item in data.get('LivesList', []):
                items.append({
                    'title': item.get('title', ''),
                    'digest': item.get('digest', ''),
                    'time': item.get('showtime', ''),
                    'url': item.get('url_w') or item.get('url_m') or '',
                    'source': '东方财富'
                })
        print(f"  [东方财富] 获取 {len(items)} 条快讯")
    except Exception as e:
        print(f"  [东方财富] 获取失败: {e}")
    return items


def fetch_wallstreet_news():
    """从华尔街见闻获取快讯"""
    items = []
    try:
        url = 'https://api-one-wscn.awtmt.com/apiv1/content/lives?channel=commodity-channel&limit=100'
        data = fetch_json(url)
        for item in data.get('data', {}).get('items', []):
            ts = item.get('display_time', 0)
            if ts:
                dt = datetime.fromtimestamp(ts, tz=BEIJING_TZ)
                time_str = dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                time_str = ''
            items.append({
                'title': item.get('title', ''),
                'digest': item.get('content_text', ''),
                'time': time_str,
                'url': f"https://wallstreetcn.com/livenews/{item.get('id', '')}" if item.get('id') else '',
                'source': '华尔街见闻'
            })
        print(f"  [华尔街见闻] 获取 {len(items)} 条快讯")
    except Exception as e:
        print(f"  [华尔街见闻] 获取失败: {e}")
    return items


def fetch_all_news():
    """获取并合并所有快讯，按今日过滤，去重"""
    all_items = fetch_eastmoney_news() + fetch_wallstreet_news()

    # 按今日过滤
    today_str = datetime.now(BEIJING_TZ).strftime('%Y-%m-%d')
    today_items = [n for n in all_items if n.get('time', '').startswith(today_str)]

    # 如果今日为空（可能是凌晨），用全部最近50条
    if not today_items:
        print(f"  今日({today_str})暂无快讯，使用最近50条")
        today_items = all_items[:50]

    # 去重（按标题前60字符，标题为空时用digest前60字符）
    seen = set()
    unique = []
    for item in today_items:
        title = item.get('title', '') or ''
        digest = item.get('digest', '') or ''
        key = title[:60] if title else digest[:60]
        if not key:
            key = f'item_{len(unique)}'  # 兜底：给无标题无摘要的条目一个唯一key
        if key not in seen:
            seen.add(key)
            unique.append(item)

    # 如果去重后仍为空，用全部最近30条（极端兜底）
    if not unique and all_items:
        print(f"  去重后为空，使用全部最近30条")
        unique = all_items[:30]

    # 如果今日快讯不足10条，补充最近的非今日快讯
    if len(unique) < 10 and len(all_items) > len(unique):
        existing_keys = set()
        for item in unique:
            title = item.get('title', '') or ''
            digest = item.get('digest', '') or ''
            key = title[:60] if title else digest[:60]
            existing_keys.add(key)
        for item in all_items:
            if len(unique) >= 30:
                break
            title = item.get('title', '') or ''
            digest = item.get('digest', '') or ''
            key = title[:60] if title else digest[:60]
            if key not in existing_keys:
                existing_keys.add(key)
                unique.append(item)

    # 按时间倒序
    unique.sort(key=lambda x: x.get('time', ''), reverse=True)
    print(f"  合计去重后: {len(unique)} 条快讯")
    return unique


def fetch_futures_prices():
    """尝试从东方财富 push2 API 获取期货价格（可选，失败不影响）"""
    try:
        secids = ",".join([c[0] for c in FUTURES_CONTRACTS])
        url = (f"https://push2.eastmoney.com/api/qt/ulist.np/get?"
               f"fields=f1,f2,f3,f4,f6,f12,f14,f15,f16,f17,f18,f169,f170"
               f"&secids={urllib.parse.quote(secids)}")
        data = fetch_json(url, timeout=10)
        items = data.get('data', {}).get('diff', []) if data.get('data') else []
        result = {}
        for item in items:
            code = item.get('f12', '')
            result[code] = {
                'name': item.get('f14', ''),
                'price': item.get('f2', 0),
                'change_pct': item.get('f3', 0),
                'change': item.get('f4', 0),
                'high': item.get('f15', 0),
                'low': item.get('f16', 0),
                'open': item.get('f17', 0),
                'prev_close': item.get('f18', 0),
                'settlement': item.get('f169', 0),
            }
        if result:
            print(f"  [push2] 获取 {len(result)} 个合约价格")
        return result
    except Exception as e:
        print(f"  [push2] 价格获取失败（不影响报告生成）: {str(e)[:60]}")
        return {}


def categorize_news(news_items):
    """按板块分类新闻"""
    categorized = {sector: [] for sector in SECTOR_KEYWORDS}
    categorized['综合'] = []

    for item in news_items:
        text = (item.get('title', '') + ' ' + item.get('digest', '')).lower()
        matched = False
        for sector, keywords in SECTOR_KEYWORDS.items():
            if any(kw.lower() in text for kw in keywords):
                categorized[sector].append(item)
                matched = True
                break
        if not matched:
            categorized['综合'].append(item)

    return categorized


def extract_gold_news(news_items):
    """提取黄金相关新闻"""
    gold_keywords = SECTOR_KEYWORDS['贵金属']
    gold_news = []
    for item in news_items:
        text = (item.get('title', '') + ' ' + item.get('digest', '')).lower()
        if any(kw.lower() in text for kw in gold_keywords):
            gold_news.append(item)
    return gold_news


# ==================== HTML 生成 ====================

def generate_today_section(date_str, news_items, futures_data):
    """生成「今日数据更新」HTML 区块"""

    now = datetime.now(BEIJING_TZ)
    gen_time = now.strftime('%Y-%m-%d %H:%M:%S')

    # 按板块分类新闻
    categorized = categorize_news(news_items)
    gold_news = extract_gold_news(news_items)

    html_parts = []

    # 区块容器
    html_parts.append(f'''
<!-- TODAY_AUTO_DATA_START -->
<div class="today-auto-section" style="
  background: var(--card-bg, #1a1a2e);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  border: 1px solid var(--border-color, #333);
">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
    <h2 style="margin:0;font-size:20px;color:var(--text-main,#eee);">
      📊 今日数据更新 · {date_str}
    </h2>
    <span style="font-size:12px;color:var(--text-muted,#888);">
      自动生成于 {gen_time}
    </span>
  </div>
''')

    # 1. 期货价格表（如果有数据）
    if futures_data:
        html_parts.append('<div style="margin-bottom:20px;">')
        html_parts.append('<h3 style="font-size:16px;color:var(--text-main,#eee);margin-bottom:10px;">📈 核心行情数据</h3>')
        html_parts.append('<p style="font-size:12px;color:var(--text-muted,#888);margin-bottom:8px;">'
                         '以下为生成时快照，<strong>实时价格请点击品种名称查看走势图</strong>。'
                         '结算价为期货每日盯市基准，比收盘价更重要。</p>')

        for sector in ['能化板块', '有色金属', '黑色系', '农产品', '贵金属']:
            sector_contracts = [c for c in FUTURES_CONTRACTS if c[3] == sector]
            sector_data = [(c, futures_data.get(c[1], {})) for c in sector_contracts
                           if c[1] in futures_data]
            if not sector_data:
                continue

            html_parts.append(f'<h4 style="font-size:14px;color:var(--accent,#6c5ce7);margin:12px 0 6px;">{sector}</h4>')
            html_parts.append('<table style="width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px;">')
            html_parts.append('<tr style="background:var(--hover-bg,#252540);">'
                            '<th style="padding:6px 8px;text-align:left;">品种</th>'
                            '<th style="padding:6px 8px;text-align:right;">开盘</th>'
                            '<th style="padding:6px 8px;text-align:right;">最高</th>'
                            '<th style="padding:6px 8px;text-align:right;">最低</th>'
                            '<th style="padding:6px 8px;text-align:right;">结算价</th>'
                            '<th style="padding:6px 8px;text-align:right;">涨跌幅</th>'
                            '</tr>')

            for (secid, code, name, _), data in sector_data:
                link = f"https://quote.eastmoney.com/qihuo/{code}.html"
                settlement = data.get('settlement', 0) or data.get('price', 0)
                html_parts.append(
                    f'<tr style="border-bottom:1px solid var(--border-color,#333);">'
                    f'<td style="padding:6px 8px;">'
                    f'<a href="{link}" target="_blank" style="color:var(--accent,#6c5ce7);text-decoration:none;">{name}</a>'
                    f'</td>'
                    f'<td style="padding:6px 8px;text-align:right;">{format_price(data.get("open",0))}</td>'
                    f'<td style="padding:6px 8px;text-align:right;color:#e74c3c;">{format_price(data.get("high",0))}</td>'
                    f'<td style="padding:6px 8px;text-align:right;color:#27ae60;">{format_price(data.get("low",0))}</td>'
                    f'<td style="padding:6px 8px;text-align:right;font-weight:600;">{format_price(settlement)}</td>'
                    f'<td style="padding:6px 8px;text-align:right;">{format_change(data.get("change_pct",0))}</td>'
                    f'</tr>'
                )
            html_parts.append('</table>')

        html_parts.append('</div>')

    # 2. 黄金聚焦
    html_parts.append('<div style="margin-bottom:20px;">')
    html_parts.append('<h3 style="font-size:16px;color:var(--text-main,#eee);margin-bottom:10px;">💰 黄金聚焦</h3>')

    if gold_news:
        html_parts.append(f'<p style="font-size:12px;color:var(--text-muted,#888);margin-bottom:8px;">'
                         f'今日黄金相关快讯 {len(gold_news)} 条，影响金价变化的事件/因素如下：</p>')
        html_parts.append('<div style="max-height:400px;overflow-y:auto;">')
        for item in gold_news[:15]:
            time_str = item.get('time', '')[11:16] if len(item.get('time', '')) > 15 else ''
            title = item.get('title', '')[:80]
            url = item.get('url', '')
            source = item.get('source', '')
            link_html = f'<a href="{url}" target="_blank" style="color:var(--accent,#6c5ce7);font-size:11px;text-decoration:none;">[{source}]</a>' if url else f'<span style="font-size:11px;color:var(--text-muted);">[{source}]</span>'
            html_parts.append(
                f'<div style="padding:6px 0;border-bottom:1px solid var(--border-color,#333);">'
                f'<span style="color:var(--text-muted,#888);font-size:11px;margin-right:6px;">{time_str}</span>'
                f'<span style="color:var(--text-main,#ddd);font-size:13px;">{title}</span> '
                f'{link_html}'
                f'</div>'
            )
        html_parts.append('</div>')
    else:
        html_parts.append('<p style="color:var(--text-muted,#888);font-size:13px;">今日暂无黄金相关快讯</p>')

    html_parts.append('</div>')

    # 3. 按板块分类的要闻分析
    html_parts.append('<div style="margin-bottom:20px;">')
    html_parts.append('<h3 style="font-size:16px;color:var(--text-main,#eee);margin-bottom:10px;">📰 今日板块要闻</h3>')

    for sector in ['能化板块', '有色金属', '黑色系', '农产品', '贵金属', '综合']:
        sector_news = categorized.get(sector, [])
        if not sector_news:
            continue

        html_parts.append(f'<details style="margin-bottom:8px;">')
        html_parts.append(f'<summary style="cursor:pointer;font-size:14px;color:var(--accent,#6c5ce7);'
                         f'padding:6px 0;font-weight:500;">'
                         f'{sector}（{len(sector_news)} 条）</summary>')
        html_parts.append('<div style="padding:8px 0 8px 16px;max-height:300px;overflow-y:auto;">')

        for item in sector_news[:20]:
            time_str = item.get('time', '')[11:16] if len(item.get('time', '')) > 15 else ''
            title = item.get('title', '')[:80]
            url = item.get('url', '')
            source = item.get('source', '')
            link_html = f'<a href="{url}" target="_blank" style="color:var(--accent,#6c5ce7);font-size:11px;text-decoration:none;">[{source}]</a>' if url else f'<span style="font-size:11px;color:var(--text-muted);">[{source}]</span>'
            html_parts.append(
                f'<div style="padding:4px 0;border-bottom:1px solid var(--border-color,#222);">'
                f'<span style="color:var(--text-muted,#888);font-size:11px;margin-right:6px;">{time_str}</span>'
                f'<span style="color:var(--text-main,#ddd);font-size:12px;">{title}</span> '
                f'{link_html}'
                f'</div>'
            )
        html_parts.append('</div></details>')

    html_parts.append('</div>')

    # 底部说明
    html_parts.append(
        '<div style="margin-top:16px;padding-top:12px;border-top:1px solid var(--border-color,#333);">'
        '<p style="font-size:11px;color:var(--text-muted,#666);margin:0;">'
        '📊 以上数据由 GitHub Action 于 ' + gen_time + ' 自动生成。'
        '实时快讯和行情价格由页面 JS 每 30 秒自动刷新，请参考页面其他模块。'
        '</p></div>'
    )

    html_parts.append('</div>\n<!-- TODAY_AUTO_DATA_END -->')

    return '\n'.join(html_parts)


# ==================== HTML 处理 ====================

def download_template():
    """下载当前页面作为模板"""
    try:
        html = fetch_url(TEMPLATE_URL)
        print(f"  模板下载成功: {len(html):,} 字节")
        return html
    except Exception as e:
        print(f"  模板下载失败: {e}")
        # 如果下载失败，尝试读取本地 index.html
        if os.path.exists('index.html'):
            with open('index.html', 'r', encoding='utf-8') as f:
                html = f.read()
            print(f"  使用本地 index.html: {len(html):,} 字节")
            return html
        raise RuntimeError("无法获取模板页面")


def update_date(html, date_str):
    """更新页面中的日期"""
    # 更新 <title> 标签
    html = re.sub(
        r'(<title>[^<]*?)\d{4}年\d{1,2}月\d{1,2}日',
        r'\1' + date_str,
        html
    )

    # 更新 header-date 中的日期
    html = re.sub(
        r'(\d{4}年\d{1,2}月\d{1,2}日)\s+星期[一二三四五六日天]',
        date_str + ' ' + get_weekday_str(),
        html
    )

    # 更新所有出现的旧日期（保留 TODAY_AUTO_DATA 区块中的日期）
    # 只替换 header 区域的日期
    html = re.sub(
        r'(class="header-date"[^>]*>.*?<span[^>]*>)\d{4}年\d{1,2}月\d{1,2}日',
        r'\1' + date_str,
        html,
        flags=re.DOTALL
    )

    return html


def get_weekday_str():
    """获取中文星期"""
    weekdays = ['星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日']
    return weekdays[datetime.now(BEIJING_TZ).weekday()]


def inject_content(html, today_section):
    """将今日数据区块注入 HTML"""

    MARKER_START = '<!-- TODAY_AUTO_DATA_START -->'
    MARKER_END = '<!-- TODAY_AUTO_DATA_END -->'

    # 如果已存在标记，替换内容
    if MARKER_START in html:
        pattern = re.escape(MARKER_START) + r'.*?' + re.escape(MARKER_END)
        html = re.sub(pattern, today_section.strip(), html, flags=re.DOTALL)
        print("  替换已有今日数据区块")
    else:
        # 首次插入：在 personal-view 前面插入
        insert_point = '<div class="personal-view">'
        if insert_point in html:
            html = html.replace(
                insert_point,
                today_section + '\n\n' + insert_point,
                1
            )
            print("  在 personal-view 前插入今日数据区块")
        else:
            # 备选：在 container 开头插入
            insert_point2 = '<div class="container" style="padding-top: 20px;">'
            if insert_point2 in html:
                html = html.replace(
                    insert_point2,
                    insert_point2 + '\n' + today_section,
                    1
                )
                print("  在 container 开头插入今日数据区块")
            else:
                # 最后手段：在 body 后插入
                html = html.replace('</body>', today_section + '\n</body>', 1)
                print("  在 body 末尾插入今日数据区块")

    return html


# ==================== 主函数 ====================

def main():
    print("=" * 50)
    print("每日期货日报自动生成")
    print("=" * 50)

    # 1. 获取北京时间
    now = datetime.now(BEIJING_TZ)
    date_str = f"{now.year}年{now.month}月{now.day}日"
    print(f"\n[1] 今日日期: {date_str} {get_weekday_str()}")

    # 2. 下载当前页面模板
    print("\n[2] 下载页面模板...")
    html = download_template()

    # 3. 更新日期
    print("\n[3] 更新页面日期...")
    html = update_date(html, date_str)

    # 4. 获取快讯
    print("\n[4] 获取今日快讯...")
    news_items = fetch_all_news()

    # 5. 尝试获取期货价格（可选）
    print("\n[5] 尝试获取期货价格...")
    futures_data = fetch_futures_prices()

    # 6. 生成今日数据区块
    print("\n[6] 生成今日数据区块...")
    today_section = generate_today_section(date_str, news_items, futures_data)

    # 7. 注入到页面
    print("\n[7] 注入内容到页面...")
    html = inject_content(html, today_section)

    # 8. 保存
    print(f"\n[8] 保存到 {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  保存成功: {len(html):,} 字节")

    print("\n" + "=" * 50)
    print("✅ 报告生成完成！")
    print(f"   日期: {date_str}")
    print(f"   快讯: {len(news_items)} 条")
    print(f"   期货价格: {len(futures_data)} 个合约" + ("（获取失败，依赖页面JS实时获取）" if not futures_data else ""))
    print(f"   输出: {OUTPUT_FILE}")
    print("=" * 50)


if __name__ == "__main__":
    main()
