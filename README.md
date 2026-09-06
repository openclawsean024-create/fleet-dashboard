# GitHub Fleet Dashboard

> 拾光設計 / Tenet Studio · 食刻設計姊妹品牌  
> 85 個 GitHub repo · v3.0.2 升級進度總覽

## 線上 Dashboard
**https://openclawsean024-create.github.io/fleet-dashboard/**

## 怎麼更新

### 1. 自動（推薦）
每小時整點 7 分自動跑一次 GHA workflow,從 GitHub API 拉最新狀態重新生成。

### 2. 手動
1. 進去 [Actions tab](https://github.com/openclawsean024-create/fleet-dashboard/actions/workflows/refresh.yml)
2. 選 `Update Dashboard`
3. 按 `Run workflow` → 選 main → `Run`
4. 等 1-2 分鐘,Pages 就更新

### 3. 改 dashboard 樣式
- `scripts/generate.py` — HTML template + 資料抓取邏輯
- 改了之後 push,workflow 自動跑

## 怎麼看進度

- ✓ **DONE** = repo 有 `PRD/SPEC.md` + `.github/workflows/*.yml` 兩個檔
- ◐ **PARTIAL** = 只有其中一個
- ⋯ **IN FLIGHT** = 兩個都沒有(background worker 還在跑)

## 觸發 GH_TOKEN
GHA 用 `secrets.GH_TOKEN` 呼叫 GitHub API。要設:
1. https://github.com/settings/tokens/new → 勾 `repo` + `read:org`
2. Fleet-dashboard repo → Settings → Secrets and variables → Actions → New repository secret
3. Name: `GH_TOKEN`,Value: 你的 PAT
