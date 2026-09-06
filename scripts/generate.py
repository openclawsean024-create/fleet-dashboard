#!/usr/bin/env python3
"""
Generate the GitHub Fleet Dashboard for openclawsean024-create.
Fetches all repos + checks v3.0.2 status from PRD/SPEC.md presence, then writes index.html.
"""
import os
import sys
import json
import re
import urllib.request
import urllib.error
from datetime import datetime
from collections import Counter

# ── Config ────────────────────────────────────────────────────────────────
GH_USER = "openclawsean024-create"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "fleet-dashboard"}
if TOKEN:
    HEADERS["Authorization"] = f"Bearer {TOKEN}"

# Vercel integration
VERCEL_TOKEN = os.environ.get("VERCEL_TOKEN")
VERCEL_TEAM_ID = os.environ.get("VERCEL_TEAM_ID")
VERCEL_HEADERS = {"Accept": "application/json", "User-Agent": "fleet-dashboard"}
if VERCEL_TOKEN:
    VERCEL_HEADERS["Authorization"] = f"Bearer {VERCEL_TOKEN}"

OUT_FILE = "index.html"

# ── Helpers ───────────────────────────────────────────────────────────────
def gh_get(url, params=None):
    """Fetch a GitHub API URL with optional query params. Returns JSON or None."""
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        if e.code == 403:
            print(f"  rate-limited at {url}", file=sys.stderr)
            return None
        raise


def list_all_repos(user):
    """List every repo owned by the user (handles pagination)."""
    repos = []
    page = 1
    while True:
        data = gh_get(f"https://api.github.com/users/{user}/repos",
                      {"per_page": 100, "page": page, "type": "owner"})
        if not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    return repos


def has_prd_spec(user, repo):
    """Return True if repo has PRD/SPEC.md (v3.0.2 spec exists)."""
    data = gh_get(f"https://api.github.com/repos/{user}/{repo}/contents/PRD/SPEC.md")
    return data is not None and "download_url" in data


def has_gha(user, repo):
    """Return True if repo has any workflow file under .github/workflows/."""
    data = gh_get(f"https://api.github.com/repos/{user}/{repo}/contents/.github/workflows")
    return data is not None and isinstance(data, list) and len(data) > 0


# ── Vercel ─────────────────────────────────────────────────────────────────
def vercel_get(path, params=None):
    """Call Vercel REST API. Returns JSON or None."""
    if not VERCEL_TOKEN:
        return None
    if params:
        from urllib.parse import urlencode
        url = f"https://api.vercel.com{path}?{urlencode(params)}"
    else:
        url = f"https://api.vercel.com{path}"
    req = urllib.request.Request(url, headers=VERCEL_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  Vercel API {e.code} at {path}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  Vercel error: {e}", file=sys.stderr)
        return None


def fetch_vercel_projects():
    """Fetch all Vercel projects → {project_name: {url, deployment_url, targets, ...}}"""
    if not VERCEL_TOKEN:
        print("  VERCEL_TOKEN not set — skipping Vercel integration")
        return {}

    projects = {}
    params = {"limit": 100}
    if VERCEL_TEAM_ID:
        params["teamId"] = VERCEL_TEAM_ID

    print("  Fetching Vercel projects...")
    data = vercel_get("/v10/projects", params)
    if not data or "projects" not in data:
        print("  No Vercel projects found or API error")
        return {}

    for p in data["projects"]:
        name = p.get("name", "").lower()
        if not name:
            continue
        targets = p.get("targets", {})
        production_alias = p.get("production_alias") or p.get("alias", [{}])[0].get("domain") if isinstance(p.get("alias"), list) else None
        # Best URL: production alias if set, else vercel.app default
        url = (production_alias or targets.get("production", {}).get("url") or
               f"https://{name}.vercel.app")
        # Latest deployment URL
        latest_deploy = p.get("latestDeployments", [{}])[0] if p.get("latestDeployments") else {}
        deploy_url = latest_deploy.get("url") if latest_deploy else None
        projects[name] = {
            "url": url if url.startswith("http") else f"https://{url}",
            "deploy_url": deploy_url,
            "framework": p.get("framework", ""),
        }

    print(f"  Got {len(projects)} Vercel projects")
    return projects


# ── Categorization ────────────────────────────────────────────────────────
def categorize(name, desc):
    full = (name + " " + desc).lower()
    rules = [
        ("🍜 餐飲",  ["restaurant", "food", "dining", "menu", "kiosk", "食刻", "餐"]),
        ("🏠 房地產", ["rental", "house", "property", "aggreg", "房"]),
        ("🛡️ 保險",  ["insurance", "claim", "保"]),
        ("💼 CRM",   ["crm", "concierge", "beauty", "美業", "客戶"]),
        ("💬 社群",  ["social", "comment", "reply", "thread", "line", "facebook", "社群"]),
        ("🤖 AI",    ["ai", "gpt", "claude", "agent", "auto"]),
        ("📚 教育",  ["train", "lms", "edu", "教", "課程"]),
        ("🏨 飯店",  ["hotel", "pm", "飯店", "民宿", "旅館"]),
        ("🎬 影音",  ["video", "audio", "music", "tts", "rap", "meme", "影音", "ebook"]),
        ("📝 內容",  ["article", "blog", "eternal", "sui", "記事"]),
        ("🔧 工具",  ["tool", "script", "mcp", "skill", "hermes"]),
        ("💊 健康",  ["health", "medical", "clinic", "glp1", "健康", "醫"]),
        ("🔮 算命",  ["fortune", "fate", "horoscope", "astrology", "numerology", "占", "算"]),
        ("🛒 電商",  ["pos", "order", "track", "shop", "店"]),
        ("📊 財報",  ["finance", "report", "wealth", "budget", "財", "報"]),
        ("💭 論壇",  ["ptt", "forum"]),
    ]
    for label, kws in rules:
        if any(k in full for k in kws):
            return label
    return "📦 其他"


PAIN_KEYWORDS = [
    (["mvp"], "MVP 快速驗證"),
    (["無", "免"], "零成本/無痛起步"),
    (["自動化"], "重複作業自動化"),
    (["ai", "生成", "generate"], "AI 降低生產門檻"),
    (["管理"], "資料集中管理"),
    (["tracking", "追蹤"], "即時進度透明化"),
    (["comment", "留言"], "留言抽獎自動化"),
    (["card", "名片"], "名片交換數位化"),
    (["對比", "比價"], "跨平台一站比較"),
    (["training", "教育"], "企業內訓成本降低"),
    (["合約", "contract"], "合約審閱效率化"),
    (["rental", "租"], "租屋資訊整合"),
    (["clinic", "診所"], "診所預約流程優化"),
    (["算命", "fortune"], "個人化命理諮詢"),
    (["pos", "pms"], "收銀/庫存數位化"),
    (["財", "finance"], "財務報表視覺化"),
    (["影音", "video"], "影音下載/轉檔"),
    (["meme", "梗圖"], "社群內容快速產出"),
    (["保", "insurance"], "保單條款透明化"),
    (["crm", "美業"], "客戶關懷自動化"),
    (["social", "社群"], "社群經營效率化"),
]

def extract_pain(name, desc):
    full = (name + " " + desc).lower()
    for kws, label in PAIN_KEYWORDS:
        if any(k in full for k in kws):
            return label
    return "— 待補 SPEC"


# ── HTML Template ─────────────────────────────────────────────────────────
HTML = '''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GitHub Fleet Dashboard · 拾光設計</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400;700;900&family=ZCOOL+XiaoWei&family=Long+Cang&family=Special+Elite&family=DM+Serif+Display&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
:root {
  --ink: #1a1410; --paper: #f5efe1; --paper-2: #ebe2cd;
  --gold: #b48a3a; --gold-dark: #8a6a2a; --red: #b83232; --red-dark: #8a2424;
  --green: #4a6b3a; --line: #2a2018; --warn: #c08a2a;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "Noto Serif TC", "Songti TC", serif;
  background: var(--paper); color: var(--ink);
  line-height: 1.5; font-size: 14px;
  background-image: repeating-linear-gradient(0deg, transparent, transparent 29px, rgba(180,138,58,0.05) 29px, rgba(180,138,58,0.05) 30px);
}
.wrap { max-width: 1400px; margin: 0 auto; padding: 32px 24px 80px; }

.hdr {
  border: 3px double var(--line); padding: 28px 32px 24px;
  background: var(--paper-2); position: relative; margin-bottom: 28px;
}
.hdr::before, .hdr::after {
  content: ""; position: absolute; width: 24px; height: 24px; border: 2px solid var(--line);
}
.hdr::before { top: -2px; left: -2px; border-right: 0; border-bottom: 0; }
.hdr::after { bottom: -2px; right: -2px; border-left: 0; border-top: 0; }
.hdr-row { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: 16px; }
.hdr-left { flex: 1; min-width: 280px; }
.brand-zh { font-family: "ZCOOL XiaoWei", serif; font-size: 14px; letter-spacing: 0.4em; color: var(--gold-dark); }
.brand-en { font-family: "DM Serif Display", serif; font-size: 44px; line-height: 1; color: var(--ink); margin: 6px 0 4px; }
.brand-en em { font-style: italic; color: var(--red); }
.subtitle { font-family: "Special Elite", monospace; font-size: 13px; letter-spacing: 0.2em; color: var(--ink); opacity: 0.7; }
.hdr-stamp {
  display: inline-block; padding: 8px 16px;
  border: 3px solid var(--red); color: var(--red);
  font-family: "ZCOOL XiaoWei", serif; font-size: 18px; letter-spacing: 0.4em;
  transform: rotate(-4deg); font-weight: 700; background: rgba(184,50,50,0.04);
}
.hdr-stamp::before { content: "✦"; margin-right: 6px; opacity: 0.6; }
.hdr-stamp::after { content: "✦"; margin-left: 6px; opacity: 0.6; }
.hdr-meta {
  margin-top: 18px; padding-top: 14px;
  border-top: 1px dashed var(--line);
  display: flex; gap: 24px; flex-wrap: wrap;
  font-family: "Special Elite", monospace; font-size: 11px; letter-spacing: 0.15em;
}
.hdr-meta span { opacity: 0.7; }
.hdr-meta strong { color: var(--red); font-weight: 700; }

.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 24px; }
.stat { border: 2px solid var(--line); padding: 14px 16px; background: var(--paper-2); position: relative; }
.stat::before { content: ""; position: absolute; top: 4px; right: 4px; width: 6px; height: 6px; background: var(--gold); }
.stat-label { font-family: "Special Elite", monospace; font-size: 10px; letter-spacing: 0.2em; opacity: 0.6; text-transform: uppercase; }
.stat-num { font-family: "DM Serif Display", serif; font-size: 36px; line-height: 1.1; margin: 4px 0 2px; }
.stat-num em { font-style: italic; color: var(--red); }
.stat-foot { font-size: 11px; opacity: 0.7; }
.stat.done { background: linear-gradient(180deg, rgba(74,107,58,0.08), transparent); }
.stat.done .stat-num { color: var(--green); }
.stat.todo { background: linear-gradient(180deg, rgba(184,50,50,0.06), transparent); }
.stat.todo .stat-num { color: var(--red); }

.pbar-wrap { border: 2px solid var(--line); padding: 18px 20px; margin-bottom: 24px; background: var(--paper-2); }
.pbar-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.pbar-title { font-family: "ZCOOL XiaoWei", serif; font-size: 16px; letter-spacing: 0.2em; }
.pbar-pct { font-family: "DM Serif Display", serif; font-size: 32px; color: var(--red); }
.pbar-pct small { font-size: 14px; color: var(--ink); opacity: 0.6; margin-left: 4px; }
.pbar-track { height: 18px; border: 2px solid var(--line); background: var(--paper); position: relative; overflow: hidden; }
.pbar-fill { height: 100%; background: repeating-linear-gradient(45deg, var(--red) 0 8px, var(--red-dark) 8px 16px); transition: width 0.6s ease; position: relative; }
.pbar-fill::after { content: ""; position: absolute; inset: 0; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent); }

.refresh-bar { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; padding: 12px 18px; border: 2px solid var(--line); background: var(--paper-2); }
.refresh-info { font-family: "Special Elite", monospace; font-size: 11px; letter-spacing: 0.15em; opacity: 0.7; }
.refresh-info code { background: var(--paper); padding: 2px 6px; border: 1px solid var(--line); font-family: "JetBrains Mono", monospace; }
.refresh-btn {
  display: inline-block; padding: 6px 14px;
  border: 2px solid var(--red); color: var(--red);
  font-family: "ZCOOL XiaoWei", serif; font-size: 13px; letter-spacing: 0.2em;
  text-decoration: none; background: transparent; cursor: pointer;
}
.refresh-btn:hover { background: var(--red); color: var(--paper); }
.refresh-btn::before { content: "🔄 "; }

.filterbar { border: 2px solid var(--line); padding: 14px 18px; margin-bottom: 16px; background: var(--paper-2); display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.filterbar-label { font-family: "Special Elite", monospace; font-size: 11px; letter-spacing: 0.15em; opacity: 0.6; margin-right: 8px; }
.fbtn { border: 1.5px solid var(--line); background: var(--paper); font-family: "Noto Serif TC", serif; font-size: 12px; padding: 4px 12px; cursor: pointer; letter-spacing: 0.05em; transition: all 0.15s; }
.fbtn:hover { background: var(--gold); color: var(--paper); }
.fbtn.active { background: var(--ink); color: var(--paper); }
.fbtn .n { font-family: "JetBrains Mono", monospace; font-size: 10px; opacity: 0.7; margin-left: 4px; }

.tbl-wrap { border: 3px double var(--line); background: var(--paper-2); overflow-x: auto; }
table { width: 100%; border-collapse: collapse; min-width: 1200px; }
th { background: var(--ink); color: var(--paper); font-family: "ZCOOL XiaoWei", serif; font-weight: 400; font-size: 13px; letter-spacing: 0.15em; padding: 12px 8px; text-align: left; border-right: 1px solid var(--gold-dark); white-space: nowrap; }
th:last-child { border-right: 0; }
td { padding: 10px 8px; border-bottom: 1px solid var(--line); vertical-align: middle; font-size: 13px; }
tr:hover td { background: rgba(180,138,58,0.08); }
tr.row-done td { opacity: 1; }
tr.row-todo td { background: rgba(184,50,50,0.04); }

.cell-mono { font-family: "JetBrains Mono", monospace; font-size: 11px; }
.cell-name { font-family: "JetBrains Mono", monospace; font-weight: 700; color: var(--ink); text-decoration: none; }
.cell-name:hover { color: var(--red); text-decoration: underline; }
.cell-cat { font-size: 13px; }
.cell-purpose { max-width: 220px; font-size: 12px; }
.cell-pain { font-size: 12px; max-width: 160px; font-style: italic; opacity: 0.85; }

.tag { display: inline-block; padding: 2px 8px; font-family: "Special Elite", monospace; font-size: 10px; letter-spacing: 0.1em; border: 1.5px solid; }
.tag-done { background: var(--green); color: var(--paper); border-color: var(--green); }
.tag-todo { background: var(--paper); color: var(--red); border-color: var(--red); }
.tag-partial { background: var(--warn); color: var(--paper); border-color: var(--warn); }

.deploy-cell { font-size: 11px; }
.deploy-link {
  display: inline-block; padding: 3px 8px;
  border: 1.5px solid var(--ink); color: var(--ink);
  text-decoration: none; font-family: "JetBrains Mono", monospace;
  font-size: 10px; letter-spacing: 0.05em;
  background: var(--paper);
  transition: all 0.15s;
}
.deploy-link:hover { background: var(--ink); color: var(--paper); }
.deploy-link.pages { border-color: var(--green); color: var(--green); }
.deploy-link.pages:hover { background: var(--green); color: var(--paper); }
.deploy-none { color: var(--ink); opacity: 0.3; font-family: "Special Elite", monospace; }

.prog-cell { min-width: 110px; }
.prog-row { display: flex; align-items: center; gap: 6px; }
.prog-mini { flex: 1; height: 8px; border: 1.5px solid var(--line); background: var(--paper); position: relative; overflow: hidden; }
.prog-mini-fill { height: 100%; background: var(--red); }
.prog-pct { font-family: "JetBrains Mono", monospace; font-size: 11px; font-weight: 700; min-width: 36px; text-align: right; }
.prog-pct.full { color: var(--green); }
.prog-pct.zero { color: var(--red); opacity: 0.5; }
.prog-pct.partial { color: var(--warn); }

.ftr { margin-top: 32px; padding-top: 18px; border-top: 2px solid var(--line); text-align: center; font-family: "Special Elite", monospace; font-size: 11px; letter-spacing: 0.2em; opacity: 0.6; }
.ftr-zh { font-family: "ZCOOL XiaoWei", serif; font-size: 14px; letter-spacing: 0.3em; opacity: 0.7; margin-bottom: 4px; }

@media print { body { background: white; } .filterbar, .refresh-bar { display: none; } }
@media (max-width: 768px) { .brand-en { font-size: 32px; } .wrap { padding: 16px 8px 60px; } }
</style>
</head>
<body>
<div class="wrap">

<header class="hdr">
  <div class="hdr-row">
    <div class="hdr-left">
      <div class="brand-zh">拾 光 設 計  ／  T E N E T  S T U D I O</div>
      <h1 class="brand-en">GitHub <em>Fleet</em> Dashboard</h1>
      <div class="subtitle">__TOTAL__ · OPENCLAWSEAN024-CREATE · v3.0.2 SPRINT</div>
    </div>
    <div class="hdr-stamp">PR D · v 3.0.2</div>
  </div>
  <div class="hdr-meta">
    <span>EST · <strong>2024</strong></span>
    <span>GENERATED · <strong>__NOW__</strong></span>
    <span>SCOPE · <strong>__TOTAL__ REPOS</strong></span>
    <span>RUN · <strong>Mavis · MiniMax-M3</strong></span>
    <span>NEXT REFRESH · <strong>HOURLY + MANUAL</strong></span>
  </div>
</header>

<div class="stats">
  <div class="stat done">
    <div class="stat-label">DONE</div>
    <div class="stat-num">__DONE__</div>
    <div class="stat-foot">PRD/SPEC + GHA both present</div>
  </div>
  <div class="stat todo">
    <div class="stat-label">IN FLIGHT</div>
    <div class="stat-num">__TODO__</div>
    <div class="stat-foot">background workers</div>
  </div>
  <div class="stat">
    <div class="stat-label">TOTAL</div>
    <div class="stat-num">__TOTAL__</div>
    <div class="stat-foot">全部 GitHub repos</div>
  </div>
  <div class="stat">
    <div class="stat-label">LANGUAGES</div>
    <div class="stat-num">__LANGS__</div>
    <div class="stat-foot">TypeScript / HTML / JS / Python / CSS / Shell</div>
  </div>
  <div class="stat">
    <div class="stat-label">CATEGORIES</div>
    <div class="stat-num">__CATS__</div>
    <div class="stat-foot">自動分類</div>
  </div>
  <div class="stat done">
    <div class="stat-label">PAGES</div>
    <div class="stat-num">__PAGES__</div>
    <div class="stat-foot">已啟用 GitHub Pages</div>
  </div>
</div>

<div class="pbar-wrap">
  <div class="pbar-head">
    <div class="pbar-title">完 工 進 度 ／ SHIP PROGRESS</div>
    <div class="pbar-pct">__PCT__<small>%</small></div>
  </div>
  <div class="pbar-track">
    <div class="pbar-fill" style="width: __PCT__%"></div>
  </div>
</div>

<div class="refresh-bar">
  <div class="refresh-info">
    自動更新：每小時跑一次 GHA workflow · 手動觸發：<code>Actions → Update Dashboard → Run workflow</code>
  </div>
  <a class="refresh-btn" href="https://github.com/openclawsean024-create/fleet-dashboard/actions/workflows/refresh.yml" target="_blank" rel="noopener noreferrer">手動更新</a>
</div>

<div class="filterbar">
  <span class="filterbar-label">FILTER  ／  分 類</span>
  <button class="fbtn active" data-filter="all">全部<span class="n">__TOTAL__</span></button>
  __CAT_BUTTONS__
  <span class="filterbar-label" style="margin-left: 16px;">狀態</span>
  <button class="fbtn active" data-status="all">All</button>
  <button class="fbtn" data-status="done">✓ Done</button>
  <button class="fbtn" data-status="todo">⋯ In Flight</button>
</div>

<div class="tbl-wrap">
<table>
<thead>
<tr>
  <th style="width: 86px;">建立</th>
  <th style="width: 86px;">更新</th>
  <th style="width: 180px;">GITHUB REPO</th>
  <th style="width: 96px;">分類</th>
  <th style="width: 200px;">專案名稱 / NAME</th>
  <th>用途</th>
  <th style="width: 150px;">解決痛點</th>
  <th style="width: 110px;">LIVE / DEPLOY</th>
  <th style="width: 72px;">進度</th>
  <th style="width: 130px;">% 進度條</th>
</tr>
</thead>
<tbody id="tbody">
__ROWS__
</tbody>
</table>
</div>

<footer class="ftr">
  <div class="ftr-zh">拾 光 設 計  ／  T E N E T  S T U D I O  ·  食 刻 設 計 姊 妹 品 牌</div>
  <div>EST · 2024 ／ PRINT-FEEL · 1970s ／ 印 章 ／ 燙 金 ／ 紅 印 泥 ／ 米 白 道 林 紙</div>
  <div style="margin-top: 4px;">Generated by Mavis · MiniMax-M3 · <span id="now"></span> · v3.0.2 fleet sprint</div>
</footer>

</div>

<script>
const rows = document.querySelectorAll('#tbody tr');
document.querySelectorAll('.fbtn[data-filter]').forEach(btn => {
  btn.addEventListener('click', () => {
    const f = btn.dataset.filter;
    document.querySelectorAll('.fbtn[data-filter]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    rows.forEach(r => { r.style.display = (f === 'all' || r.dataset.cat === f) ? '' : 'none'; });
  });
});
document.querySelectorAll('.fbtn[data-status]').forEach(btn => {
  btn.addEventListener('click', () => {
    const s = btn.dataset.status;
    document.querySelectorAll('.fbtn[data-status]').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    rows.forEach(r => { r.style.display = (s === 'all' || r.dataset.status === s) ? '' : 'none'; });
  });
});
document.getElementById('now').textContent = new Date().toLocaleString('zh-TW', { hour12: false });
setTimeout(() => location.reload(), 1000 * 60 * 30); // auto-reload every 30 min
</script>
</body>
</html>'''


# ── Main ──────────────────────────────────────────────────────────────────
def main():
    print(f"Fetching all repos for {GH_USER}...")
    all_repos = list_all_repos(GH_USER)
    print(f"  Found {len(all_repos)} repos total")

    # Filter out archived + forks
    fleet = [r for r in all_repos if not r.get("archived") and not r.get("fork")]
    print(f"  After filtering: {len(fleet)} active repos")

    # Get current HEAD commit SHA for each (for status)
    # 85 = top active by ranking

    # Fetch Vercel projects (if token available)
    vercel_projects = fetch_vercel_projects()

    rows = []
    print("  Checking PRD/SPEC.md + GHA presence for each repo...")
    for i, r in enumerate(fleet, 1):
        name = r["name"]
        has_spec = has_prd_spec(GH_USER, name)
        has_wf = has_gha(GH_USER, name)
        if has_spec and has_wf:
            status = "done"
            pct = 100
        elif has_spec or has_wf:
            status = "partial"
            pct = 50
        else:
            status = "todo"
            pct = 0
        rows.append({
            "name": name,
            "url": r["html_url"],
            "created_at": r["created_at"][:10],
            "updated_at": r["updated_at"][:10],
            "language": r.get("language") or "—",
            "description": r.get("description") or "",
            "has_pages": r.get("has_pages", False),
            "category": categorize(name, r.get("description") or ""),
            "purpose": (r.get("description") or "—")[:80],
            "pain": extract_pain(name, r.get("description") or ""),
            "status": status,
            "pct": pct,
            "vercel_url": vercel_projects.get(name.lower(), {}).get("url"),
        })
        if i % 10 == 0:
            print(f"    {i}/{len(fleet)}")

    # Sort: todo first, then by updated_at desc
    rows.sort(key=lambda x: (0 if x["status"] != "done" else 1,
                            -(datetime.fromisoformat(x["updated_at"]).timestamp())))

    # Stats
    total = len(rows)
    done = sum(1 for r in rows if r["status"] == "done")
    todo = total - done
    pct_overall = round(done / total * 100, 1) if total else 0
    langs = set(r["language"] for r in rows if r["language"] and r["language"] != "—")
    pages = sum(1 for r in rows if r["has_pages"])
    cat_counts = Counter(r["category"] for r in rows)

    # Build category buttons
    cat_btns = ""
    for cat, n in cat_counts.most_common():
        cat_btns += f'<button class="fbtn" data-filter="{cat}">{cat}<span class="n">{n}</span></button>\n  '

    # Build rows
    rows_html = ""
    for d in rows:
        if d["status"] == "done":
            row_class = "row-done"
            tag_class = "tag-done"
            tag_text = "✓ DONE"
        elif d["status"] == "partial":
            row_class = "row-partial"
            tag_class = "tag-partial"
            tag_text = "◐ PARTIAL"
        else:
            row_class = "row-todo"
            tag_class = "tag-todo"
            tag_text = "⋯ IN FLIGHT"

        if d["pct"] == 100:
            pct_cls = "full"
        elif d["pct"] == 0:
            pct_cls = "zero"
        else:
            pct_cls = "partial"

        # Build deploy cell
        vercel_url = d.get('vercel_url')
        if vercel_url:
            deploy_html = f'<a class="deploy-link" href="{vercel_url}" target="_blank" rel="noopener noreferrer">▲ Vercel ↗</a>'
        elif d['has_pages']:
            pages_url = f"https://{GH_USER}.github.io/{d['name']}/"
            deploy_html = f'<a class="deploy-link pages" href="{pages_url}" target="_blank" rel="noopener noreferrer">▤ Pages ↗</a>'
        else:
            deploy_html = '<span class="deploy-none">—</span>'

        rows_html += f'''<tr class="{row_class}" data-cat="{d['category']}" data-status="{d['status']}">
  <td class="cell-mono">{d['created_at']}</td>
  <td class="cell-mono">{d['updated_at']}</td>
  <td><a class="cell-name" href="{d['url']}" target="_blank" rel="noopener noreferrer">{d['name']} ↗</a></td>
  <td class="cell-cat">{d['category']}</td>
  <td><span class="cell-mono">{d['name']}</span></td>
  <td class="cell-purpose">{d['purpose']}</td>
  <td class="cell-pain">{d['pain']}</td>
  <td class="deploy-cell">{deploy_html}</td>
  <td><span class="tag {tag_class}">{tag_text}</span></td>
  <td class="prog-cell">
    <div class="prog-row">
      <div class="prog-mini"><div class="prog-mini-fill" style="width: {d['pct']}%"></div></div>
      <span class="prog-pct {pct_cls}">{d['pct']}%</span>
    </div>
  </td>
</tr>
'''

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = (HTML
            .replace("__TOTAL__", str(total))
            .replace("__DONE__", str(done))
            .replace("__TODO__", str(todo))
            .replace("__LANGS__", str(len(langs)))
            .replace("__CATS__", str(len(cat_counts)))
            .replace("__PAGES__", str(pages))
            .replace("__PCT__", str(pct_overall))
            .replace("__NOW__", now)
            .replace("__CAT_BUTTONS__", cat_btns)
            .replace("__ROWS__", rows_html))

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ Wrote {OUT_FILE} ({len(html)} bytes)")
    print(f"   Done: {done}/{total} ({pct_overall}%)")
    print(f"   Categories: {len(cat_counts)}, Languages: {len(langs)}")


if __name__ == "__main__":
    main()
