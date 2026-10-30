# 人聲／伴奏分離器（Stem Splitter）· PWA

本機 Demo：上傳音訊 → 分離 **人聲（vocals）** 與 **伴奏（instrumental）** → 瀏覽器預覽與下載。  
支援 **PWA**（可加到手機主畫面）。

Local demo: upload audio → split into **vocals** + **instrumental** → preview & download.  
Also a **Progressive Web App** (installable).

---

## 功能模式 / Modes

| 模式 | UI 標籤 | 說明 |
|------|---------|------|
| `split`（預設） | 人聲／伴奏 | 輸出人聲 + 伴奏 |
| `vocal_remover` | 人聲消除 · Vocal Remover | 主要輸出伴奏／卡拉OK；有人聲軌時一併提供 |

上傳時以 multipart 欄位 `mode` 傳送。StemSplit 在 `vocal_remover` 時使用 `outputType: INSTRUMENTAL`；本機 Demucs／ffmpeg 仍走雙軌，但 UI 以伴奏為主。


---

## 分離引擎 / Separation engine

| 優先序（`STEM_PROVIDER=auto`） | 引擎 | 說明 |
|--------|------|------|
| 1 | **StemSplit API** | 雲端 AI（需 `STEMSPLIT_API_KEY`；金鑰**只放伺服器**） |
| 2 | **Demucs** `htdemucs` + `--two-stems=vocals` | 本機 AI（需 `torch` + `demucs`） |
| 3 | **ffmpeg 中置／側邊** | 後備：立體聲 mid≈人聲、side≈伴奏 |

- 若設定了 `STEMSPLIT_API_KEY`，預設會優先走 StemSplit。  
- 可用 `STEM_PROVIDER=stemsplit|demucs|ffmpeg|auto` 強制指定。

---

## 快速開始 / Quick start

```bash
cd /workspace/stem-splitter
./start.sh
```

開啟：<http://127.0.0.1:8765/>

### 使用 StemSplit（建議）

1. 到 https://stemsplit.io 註冊，於 **Settings → API Keys** 建立金鑰（新帳號有免費試用分鐘）。  
2. **只在伺服器**設定環境變數後重啟（勿放入前端或 git）：

```bash
export STEMSPLIT_API_KEY="sk_live_xxxxxxxx"
# 可選：
# export STEM_PROVIDER=stemsplit          # 強制；預設 auto 在有 key 時會選 stemsplit
# export STEMSPLIT_BASE_URL=https://stemsplit.io
# export STEMSPLIT_QUALITY=BALANCED       # FAST | BALANCED | BEST
# export STEMSPLIT_OUTPUT_FORMAT=WAV      # WAV | MP3 | FLAC
./start.sh
```

3. 確認健康檢查：

```bash
curl -s http://127.0.0.1:8765/api/health | python3 -m json.tool
```

應看到 `"stemsplit_configured": true` 與 `"provider": "stemsplit"`。

流程（伺服器代打）：presign upload → PUT 檔案 → `POST /api/v1/jobs`（`outputType: BOTH`）→ poll → 下載人聲／伴奏到 `data/outputs/<job_id>/`。

詳細比較見 [`API-OPTIONS.md`](./API-OPTIONS.md)。

### 可選：本機 Demucs

```bash
cd /workspace/stem-splitter
python3 -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
INSTALL_DEPS=0 ./start.sh
```

或一次：`INSTALL_DEPS=1 ./start.sh`

### 環境變數

| 變數 | 預設 | 說明 |
|------|------|------|
| `PORT` | `8765` | 服務埠 |
| `HOST` | `0.0.0.0` | 綁定位址 |
| `STEM_PROVIDER` | `auto` | `auto` / `stemsplit` / `demucs` / `ffmpeg` |
| `STEMSPLIT_API_KEY` | （空） | StemSplit Bearer token；**勿提交到 git** |
| `STEMSPLIT_BASE_URL` | `https://stemsplit.io` | API 根網址 |
| `STEMSPLIT_QUALITY` | `BALANCED` | `FAST` / `BALANCED` / `BEST` |
| `STEMSPLIT_OUTPUT_FORMAT` | `WAV` | `WAV` / `MP3` / `FLAC` |
| `DEMUCS_MODEL` | `htdemucs` | Demucs 模型名 |
| `DEMUCS_DEVICE` | `cpu` | `cpu` / `cuda` |
| `DEMUCS_SEGMENT` | `7` | 愈小愈省 RAM |
| `INSTALL_DEPS` | `0` | `1` 時嘗試 pip 安裝依賴 |

---

## PWA：加到主畫面 / Add to Home Screen

已包含：

- `static/manifest.webmanifest`（standalone、主題色、192／512 icons）
- `static/sw.js`（快取 App Shell，利於可安裝性）
- Apple／主題 meta（`apple-mobile-web-app-capable`、`theme-color` 等）

### Android（Chrome）
1. 用 Chrome 開啟網站（`localhost` 或 HTTPS）。
2. 選單 → **安裝應用程式**／**加到主畫面**，或點頁面「安裝」橫幅。

### iOS（Safari）
1. 用 **Safari** 開啟。
2. 分享 → **加入主畫面** → 新增。
3. 從主畫面圖示以全螢幕開啟。

離線可開已快取的介面殼層；上傳／分離仍需連到本機伺服器（StemSplit 路徑另需外網）。

---

## 資料目錄

```
/workspace/stem-splitter/
  app.py                 # stdlib HTTP 伺服器
  stemsplit_client.py    # StemSplit REST 客戶端（金鑰僅伺服器）
  start.sh
  requirements.txt
  templates/index.html
  static/                # CSS/JS、manifest、SW、icons
  data/uploads/<job_id>/
  data/outputs/<job_id>/{vocals,instrumental}.{wav|mp3|flac}
```

`data/` 已 `.gitignore`。任務以 UUID 隔離。**請勿**把 API key 寫進程式碼或前端。

---

## 限制 / Limitations

- 建議音檔短於約 **3–5 分鐘**（過長會警告）。StemSplit 官方上限另見其文件（最長約 120 分鐘、500 MB）。
- **ffmpeg 後備**僅適合「人聲大致置中」的立體聲流行曲。
- Demucs 在 CPU 上較慢、吃 RAM；可調 `DEMUCS_SEGMENT`。
- 僅 **人聲／伴奏**；鼓／貝斯尚未接 UI。
- Service worker **不**快取上傳檔或 stems。

---

## API 摘要

- `GET /api/health` — 含 `provider`、`stemsplit_configured`、`engine` 等
- `POST /api/upload`（multipart `file`）
- `GET /api/jobs/{id}`
- `GET /api/jobs/{id}/stream/{vocals|instrumental}`
- `GET /api/jobs/{id}/download/{vocals|instrumental}`

---

## 授權

StemSplit、Demucs／模型請遵循各上游授權與服務條款。本 Demo 供本機／實驗整合。
