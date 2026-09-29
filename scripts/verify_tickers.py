#!/usr/bin/env python3
r"""verify_tickers.py — L3 pre-commit hook 拦截:扫描 staged 文件里所有
ticker 模式 (\d+\.SHG/HK/US/T/PA/...),对每个查 ticker_truth.csv 验证旁边的中文名是否匹配。
不匹配 → 阻止 commit,要求人工修复。

用法:
  # 手动: 扫描某个文件
  python scripts/verify_tickers.py path/to/file.html

  # 装 git pre-commit hook:
  python scripts/install_pre_commit.py

退出码:
  0 = 全 pass / 没找到 ticker
  1 = 有 mismatch / 阻止 commit
  2 = 读取文件或 Git 索引失败
"""
import os, re, sys, csv, subprocess, io, json
from html.parser import HTMLParser
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ticker_truth import lookup_by_ticker

# 匹配 ticker:数字.SHG / .SHE / .HK / .US / .T / .PA / .LSE / .TO 等
TICKER_RE = re.compile(r"\b(\d{4,6}(?:\.[A-Z]{1,4})?|[A-Z]{1,5}\.(?:US|HK|T|PA|LSE|TO|OL|L))\b")

# 中文公司名匹配 — 在 ticker ±60 字符窗口找
ZH_NAME_RE = re.compile(r"[一-鿿]{2,12}")  # 2-12 个中文字


def _name_matches(claimed, truth_zh, truth_en):
    """只比较公司身份；不能凭共有“科技”或“Technologies”放过错公司。"""
    clean = lambda value: re.sub(r"\([^)]*\)|（[^）]*）", "", value or "").strip()
    c = clean(claimed)
    tz, te = clean(truth_zh), clean(truth_en)
    if not c:
        return True
    if c.casefold() in {tz.casefold(), te.casefold()}:
        return True
    claimed_zh = ZH_NAME_RE.findall(c)
    actual_zh = ZH_NAME_RE.findall(tz)
    generic = {"inc", "incorporated", "corp", "corporation", "co", "company",
               "ltd", "limited", "plc", "holdings", "holding", "group",
               "technologies", "technology", "class", "common", "stock", "shares"}
    def english_brand(value):
        # 中英混写、CamelCase 缩写和 F5 这类字母数字商号仍保留身份。
        split = re.sub(r"([a-z])([A-Z])", r"\1 \2", value).lower()
        return next((w for w in re.findall(r"[a-z][a-z0-9]*", split)
                     if len(w) >= 2 and w not in generic), None)
    brand = english_brand(c)
    english_match = bool(brand and brand in {english_brand(tz), english_brand(te)})
    if claimed_zh and actual_zh:
        if any(a.startswith(b) or b.startswith(a) for a in claimed_zh for b in actual_zh):
            return True
        # 英文身份已吻合时允许中英混写的行业尾注、中文译名的长共同前缀。
        # 完全不同的中文公司名仍不能被附加的正确英文公司名掩盖。
        return english_match and any(
            a in b or b in a or
            len(os.path.commonprefix((a, b))) >= max(3, (min(len(a), len(b)) * 2 + 2) // 3)
            for a in claimed_zh for b in actual_zh)
    return english_match


def _check_pairs(path, pairs, mentioned=()):
    mismatches, warnings, checked = [], [], set()
    infos = {}
    for ticker, claimed in pairs:
        key = (ticker, claimed)
        if key in checked:
            continue
        checked.add(key)
        if ticker not in infos:
            infos[ticker] = lookup_by_ticker(ticker)
        info = infos[ticker]
        if not info:
            continue
        tz = (info.get("name_zh") or "").strip()
        te = (info.get("name_en") or "").strip()
        if _name_matches(claimed, tz, te):
            continue
        if ZH_NAME_RE.search(claimed) and not ZH_NAME_RE.search(tz) and not re.search(r"[A-Za-z]{2,}", claimed):
            warnings.append(f"{path}:{ticker} 公司名'{claimed}' — 真值仅含英文 '{te or tz}'，中文别名需核对")
            continue
        mismatches.append({"file": path, "ticker": ticker, "claimed_zh": claimed,
                           "truth_zh": tz, "truth_en": te})
    for ticker in sorted(set(mentioned) | {t for t, _ in checked}):
        info = infos[ticker] if ticker in infos else lookup_by_ticker(ticker)
        if not info:
            warnings.append(f"{path}:{ticker} — NOT IN TICKER_TRUTH DB(请跑 init/resolve)")
    return mismatches, warnings


class _Node:
    def __init__(self, tag="", attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []

    def nodes(self):
        for child in self.children:
            if isinstance(child, _Node) and child.tag not in ("script", "style"):
                yield child
                yield from child.nodes()

    def text(self):
        return " ".join(child if isinstance(child, str) else child.text()
                        for child in self.children if not isinstance(child, _Node) or
                        child.tag not in ("script", "style"))

    def has_class(self, name):
        return name in (self.attrs.get("class") or "").split()


class _ReportParser(HTMLParser):
    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
            "meta", "param", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.stack[-1])
        self.stack[-1].children.append(node)
        if tag not in self.VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, text):
        self.stack[-1].children.append(text)


def _tickers(text):
    return {m.group(1) for m in TICKER_RE.finditer(text or "") if "." in m.group(1)}


def _company_name(text, ticker=""):
    # 名称与行业说明用模板既有分隔符隔开；不从描述句里猜公司。
    name = re.split(r"[·•]|——|\s/\s|\s[—–]\s", text.strip(), maxsplit=1)[0]
    if ticker:
        name = name.replace(ticker, "")
    return name.strip(" \t\r\n()（）:：,，;；⭐")


def _html_pairs(text):
    """仅关联同一结构化卡片或姓名标签中的 ticker/公司，绝不跨标签找中文。"""
    parser = _ReportParser()
    parser.feed(text)
    nodes = list(parser.root.nodes())
    mentioned = set()
    for node in nodes:
        for value in node.attrs.values():
            mentioned.update(_tickers(value))
        for child in node.children:
            if isinstance(child, str):
                mentioned.update(_tickers(child))
    by_code = {}
    for ticker in mentioned:
        by_code.setdefault(ticker.split(".")[0], set()).add(ticker)
    pairs = []

    def emit(ticker, label):
        name = _company_name(label, ticker)
        # 标签只有证券代码时不是公司名声明。
        if name and name != ticker.split(".")[0] and re.search(r"[A-Za-z一-鿿]", name):
            pairs.append((ticker, name))

    for node in nodes:
        if node.has_class("cnode"):
            ticker = node.attrs.get("data-id", "")
            if ticker not in _tickers(ticker):
                continue
            label = next((x.text() for x in node.nodes() if x.tag in ("b", "strong")), "")
            emit(ticker, label)
            desc = node.attrs.get("data-desc", "")
            # data-desc 的首段在现有报告模板中明确是公司名。
            if re.search(r"——|\s/\s|\s[—–]\s", desc):
                emit(ticker, desc)
        if node.has_class("row"):
            descendants = list(node.nodes())
            ticker_cell = next((x for x in descendants if x.has_class("tk")), None)
            name_cell = next((x for x in descendants if x.has_class("nmcell")), None)
            if ticker_cell and name_cell:
                ticker_text = ticker_cell.text() + " " + " ".join(ticker_cell.attrs.values()) + " " + " ".join(
                    value or "" for x in ticker_cell.nodes() for value in x.attrs.values())
                tickers = _tickers(ticker_text)
                title = next((x.text() for x in name_cell.nodes() if x.has_class("t")), "")
                if len(tickers) == 1 and title:
                    emit(next(iter(tickers)), title)
        if node.has_class("candidate") or node.has_class("card"):
            code = node.attrs.get("data-ticker") or node.attrs.get("data-symbol") or ""
            symbols = _tickers(code) or by_code.get(code, set())
            title = next((x for x in node.nodes() if x.tag in ("h3", "h4")), None)
            if len(symbols) == 1 and title:
                ticker = next(iter(symbols))
                label = title.text()
                label = re.sub(r"^" + re.escape(code) + r"\s+", "", label)
                emit(ticker, label)
        if node.tag in ("b", "strong"):
            # <b>公司名(TICKER)</b> 是声明；<b>TICKER</b> 后的论点不是。
            label = node.text().strip()
            match = re.fullmatch(r"(.{2,80}?)\s*[（(]\s*([^()（）]+)\s*[)）]", label)
            if match and match.group(2) in _tickers(match.group(2)):
                emit(match.group(2), match.group(1))
    return pairs, mentioned


def scan_file(path, text=None):
    """扫单个文件,返回 (mismatches, warnings) lists
    SKIP 机制:
    - 文件首 500 字符内含 'ticker-verify: skip' → 跳过(文档/示例文件用)
    - 路径里含 _scan_*.json / _etf_audit_*.json / _gen_*.py → 跳过(raw 数据/生成器文件,
      ticker 已在 L2 verify_pair 验证,这里再扫会被字段 text 误识别为公司名 false positive)"""
    if text is None and not os.path.exists(path): return ([], [])
    # 跳过 raw data / generator 文件(2026-06-05 Dogfood #13 教训)
    base = os.path.basename(path)
    if (base.startswith("_scan_") and (base.endswith(".json") or base.endswith(".py"))) \
       or base.startswith("_etf_audit_") \
       or base.startswith("_gen_") \
       or base.startswith("_score_") \
       or base.endswith(".py") \
       or base in ("ticker_truth.csv", "scorecard.md", "theme_benchmark.csv", "SKILL.md", "lessons.md", "report_template.html"):  # .py 脚本里 ticker 是代码字面量非名称声明;生成物/truth/文档/模板骨架(edge-list 权重标签非公司名)不自我 verify
        return ([], [])
    if text is None:
        try:
            with open(path, encoding="utf-8-sig") as f:
                text = f.read()
        except Exception as e:
            return ([], [f"can't read {path}: {e}"])
    # SKIP magic comment(允许文档文件含错例示意)
    if "ticker-verify: skip" in text[:500]:
        return ([], [])
    if path.lower().endswith(".html"):
        pairs, mentioned = _html_pairs(text)
        return _check_pairs(path, pairs, mentioned)
    # company_desc.md 专用精确解析(2026-06-05 Dogfood #15 教训:通用窗口启发式产生 156 个 false positive)
    # 行格式: - **TICKER** [YYYY-MM-DD] = 公司名,描述...
    if os.path.basename(path) == "company_desc.md":
        line_re = re.compile(r'^- \*\*([\w\.\-]+(?:\.[A-Z]{1,4})?)\*\*(?:\s*\[\d{4}-\d{2}-\d{2}\])?\s*=\s*([^,,(（。]+)', re.M)
        pairs = []
        for m in line_re.finditer(text):
            ticker, claimed = m.group(1).strip(), m.group(2).strip()
            if "." not in ticker: continue
            pairs.append((ticker, claimed))
        return _check_pairs(path, pairs)

    if path.lower().endswith('.json'):
        value = json.loads(text)
        pairs = []
        def visit(item):
            if isinstance(item, dict):
                ticker = item.get('ticker') or item.get('eodhd_symbol') or item.get('tk')
                name = item.get('name_zh') or item.get('name') or item.get('t')
                if isinstance(ticker, str) and ticker in _tickers(ticker) and isinstance(name, str):
                    pairs.append((ticker, _company_name(name, ticker)))
                for child in item.values(): visit(child)
            elif isinstance(item, list):
                for child in item: visit(child)
        visit(value)
        return _check_pairs(path, pairs, _tickers(text))

    if path.lower().endswith('.md'):
        # Documentation code examples are not company-name declarations.
        prose = re.sub(r'```.*?```', '', text, flags=re.S)
        pairs = []
        pattern = r'(?:\*\*)?([A-Za-z一-鿿][A-Za-z0-9一-鿿 .&-]{1,60}?)(?:\*\*)?\s*[（(]\s*`?([A-Za-z0-9.\-]+)`?\s*[)）]'
        for name, ticker in re.findall(pattern, prose):
            if ticker in _tickers(ticker):
                pairs.append((ticker, name.strip()))
        return _check_pairs(path, pairs, _tickers(text))
    # CSV-aware scan(forward_picks.csv 用,精确取 ticker col + name_zh col,避免被 tier 字段误抓)
    if path.endswith(".csv"):
        import csv as _csv
        pairs = []
        try:
            with io.StringIO(text) as f:
                reader = _csv.reader(f)
                header = next(reader, None)
                # forward_picks schema: date,theme,ticker,name_zh,tier,...
                if header and len(header) >= 4 and ("symbol" in header[2].lower() or "ticker" in header[2].lower()) and "name" in header[3].lower():
                    for row in reader:
                        if len(row) < 4: continue
                        ticker, claimed_zh = row[2].strip(), row[3].strip()
                        if not ticker or not claimed_zh: continue
                        pairs.append((ticker, claimed_zh))
        except csv.Error as exc:
            return [], [f"can't parse {path}: {exc}"]
        return _check_pairs(path, pairs)

    mismatches = []
    warnings = []
    STOPWORDS = {"上游", "中游", "下游", "系统", "对照", "扩列", "排除", "观望", "候选",
                 "深度", "回调", "启动", "等止跌", "等启动", "已涨", "未启动", "本主题",
                 "等回调", "无独立", "持续跌", "持平", "极深", "中位", "边缘", "测试",
                 "代码", "现价", "数据", "区间", "动量", "目标", "情景", "风险"}
    # 找所有 ticker 出现位置
    seen = set()
    for m in TICKER_RE.finditer(text):
        ticker = m.group(1)
        if not (ticker.endswith(".SHG") or ticker.endswith(".SHE") or ticker.endswith(".HK")
                or ticker.endswith(".US") or "." in ticker):
            continue
        # 取 ticker 后 60 字符为主(典型报告里 ticker 后跟公司名)+ 前 30 字符 fallback
        after = text[m.end(): min(len(text), m.end() + 60)]
        before = text[max(0, m.start() - 30): m.start()]
        # 抓最近的中文名(after 优先 → before 兜底)
        zh = None
        for ctx in (after, before):
            for z in ZH_NAME_RE.findall(ctx):
                if z not in STOPWORDS and not any(s in z for s in ("rng", "off", "ext")):
                    zh = z; break
            if zh: break
        if not zh:
            continue
        key = (ticker, zh)
        if key in seen: continue
        seen.add(key)
        # 查 ground truth
        info = lookup_by_ticker(ticker)
        if not info:
            warnings.append(f"{path}:{ticker} 旁注'{zh}' — NOT IN TICKER_TRUTH DB(请跑 init/resolve)")
            continue
        truth_zh = (info.get("name_zh", "") or "").strip()
        truth_en = (info.get("name_en", "") or "").strip()
        # 双向 contains 检查
        if zh in truth_zh or truth_zh in zh:
            continue  # ok
        # 写英文情况(rare)
        if any(c.lower() in truth_en.lower() for c in [zh]) or any(p.lower() in truth_en.lower() for p in zh.split()):
            continue
        mismatches.append({
            "file": path, "ticker": ticker, "claimed_zh": zh,
            "truth_zh": truth_zh, "truth_en": truth_en,
        })

    return mismatches, warnings


def _repo_root():
    return os.path.normpath(os.path.join(HERE, ".."))


def get_staged_files(root=None):
    """git diff --cached --name-only"""
    r = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACM", "-z"],
                       capture_output=True, check=True, cwd=root or _repo_root())
    return [f for f in r.stdout.decode("utf-8").split("\0") if f]


def read_staged_file(path, root=None):
    result = subprocess.run(["git", "show", ":" + path], capture_output=True,
                            check=True, cwd=root or _repo_root())
    return result.stdout.decode("utf-8-sig")


def main():
    staged = "--staged" in sys.argv
    if staged:
        try:
            files = get_staged_files()
        except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
            print(f"[ERROR] 无法读取暂存文件清单: {type(exc).__name__}")
            return 2
        if not files:
            print("verify_tickers: no staged files")
            return 0
        targets = files
    elif len(sys.argv) > 1:
        targets = [a for a in sys.argv[1:] if not a.startswith("--")]
    else:
        print(__doc__); return 0

    # 只扫文本类
    OK_EXT = (".py", ".html", ".csv", ".md", ".json", ".txt")
    targets = [t for t in targets if t.endswith(OK_EXT)]

    if not targets:
        print("verify_tickers: no scannable files (.py/.html/.csv/.md/.json)")
        return 0

    all_mis = []
    all_warn = []
    for t in targets:
        # 用绝对路径
        if not os.path.isabs(t):
            root = _repo_root()
            t_abs = os.path.normpath(os.path.join(root, t))
        else:
            t_abs = t
        try:
            m, w = scan_file(t_abs, read_staged_file(t) if staged else None)
        except (OSError, ValueError, subprocess.CalledProcessError, UnicodeError) as exc:
            print(f"[ERROR] 无法读取暂存文件 {t}: {type(exc).__name__}")
            return 2
        all_mis.extend(m)
        all_warn.extend(w)

    print(f"verify_tickers · scanned {len(targets)} files")
    if all_warn:
        print(f"\n[WARN] {len(all_warn)} 项需核对（真值缺失或别名资料不足）:")
        for w in all_warn[:15]:
            print(f"  - {w}")

    if all_mis:
        print(f"\n[FAIL] {len(all_mis)} MISMATCH(ES) — 阻止 commit:")
        for m in all_mis:
            print(f"  [FAIL]{m['file']}: {m['ticker']} 旁注 '{m['claimed_zh']}'")
            print(f"     truth name_zh: '{m['truth_zh']}'")
            print(f"     truth name_en: '{m['truth_en']}'")
        print(f"\n修复建议:")
        print(f"  1. 用 EODHD search 重核公司名 + ticker")
        print(f"  2. 如果 ticker 错 → 改 ticker;如果文件里中文名错 → 改中文名")
        print(f"  3. 重 commit")
        return 1

    print("[PASS] 未发现明确公司错配" + ("；以上警告仍需人工核对" if all_warn else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
