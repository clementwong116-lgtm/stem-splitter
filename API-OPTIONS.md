# Stem Splitter API／模型選項比較（研究筆記）

> 研究日期：2026-10-29（Asia/Hong_Kong）  
> 目的：為 `/workspace/stem-splitter` PWA（音樂教育／音樂科技）選現成 API 或開源模型，而非自研分離網路。  
> 價格皆來自公開官網／文件；未公開者以 **unknown** 標示，勿自行推估。

現有 MVP：Python 靜態／本機伺服器，優先 Demucs `htdemucs --two-stems=vocals`，否則 ffmpeg mid/side 後備。

---

## 一、商業 API 比較表

| 選項 | Stems | 託管 | 公開價格（約） | 延遲／品質筆記 | 整合難度 | 授權／商用 | Docs |
|------|-------|------|----------------|----------------|----------|------------|------|
| **LALAL.AI API v1** | 人聲+伴奏；多 stem（鼓／貝斯／鋼琴等，**每種 stem type 分別計費**） | SaaS | **Pro $15/mo**（年付 $180，含 250 Fast 分鐘／月 + Unlimited Relaxed）或 **Top-up**：750 min/$50、3000/$190、5000/$300。Starter 無 API。計費：`時長 × stem 類型數`。 | 品質高（Orion 等專有模型）；Fast≈優先、Relaxed=排隊。第三方測試約 ~1 分鐘級／曲（非官方）。 | 中：`X-License-Key`；upload → split → poll；有 Python 範例 | 消費級 Pro／Top-up 即可用公有 API（見下）；大規模 SaaS 另有 Business／Enterprise | https://www.lalal.ai/api/v1/docs/ · https://www.lalal.ai/pricing/ |
| **StemSplit** | VOCALS／INSTRUMENTAL／BOTH／FOUR_STEMS／SIX_STEMS | SaaS | 註冊 **5 免費分鐘**；$2/10min、$5/30、$12/100、$30/300（≈$0.10–0.20/min）；**點數不過期、無訂閱**；一次 job 含所選全部 stems | Demucs 系；FAST/BALANCED/BEST；約 20–60s／音訊分鐘（官網估算） | **低**：REST + 可選 SDK；presign upload 或 `sourceUrl`；webhook | 面向 indie／開發者；信用點即 API 額度 | https://stemsplit.io/developers/docs · https://stemsplit.io/pricing |
| **Music AI**（原 Moises Developer／developer.moises.ai） | 人聲、伴奏、鼓／貝斯／吉他／鍵／弦／管風等（依 workflow／module） | SaaS | **PAYG**：Musical stems（Vocals 等）**$0.07/min／stem**；Instrumental stem **$0.05/min**；Professional $25/mo 約 5% 折扣。多 stem 會疊加。 | 教育／練習產品強；需建 workflow；延遲視佇列 | 中：upload → POST `/job` → poll；有 Node／Python 生態 | 公開開發者平台；Enterprise 另議 | https://music.ai/docs/api/reference/ · https://music.ai/pricing/ |
| **AudioShake** | vocals、instrumental、drums、bass、guitar、piano、keys、strings、wind、drum_kit 等 | SaaS | 以 **credit** 計（多數 stem **1.0 credit／min／target**）；**USD／credit 官網未公開** → **unknown**。儀表板購點。 | 製片／版權合規向；async + webhook；品質偏專業 | 中：`POST /tasks` + poll／webhook；可 URL 或 assetId | 開發者可自助；大量需 Enterprise | https://developer.audioshake.ai/ · https://developer.audioshake.ai/billing |
| **Replicate** `ryan5453/demucs` | vocals／drums／bass／other（+ no_*）；可選 6s guitar/piano | 託管 GPU（按秒） | 頁面估約 **~$0.0062／次 run**（隨輸入時長變動；A100）；按硬體秒數計費 | 開源 Demucs；短曲可數秒級；冷啟動可能較慢 | **低**：HTTP predict；適合 MVP 試 | 託管方便；**底層 Demucs 權重商用需留意**（見開源節） | https://replicate.com/ryan5453/demucs |
| **Hugging Face Inference** | 視模型卡（Demucs／UVR 等社群模型） | Serverless／Endpoint | 視方案；免費額度有限、生產常需付費 Endpoint → 具體價依帳號／硬體 **需當下查** | 品質=所選模型；佇列／冷啟動不穩 | 中：Inference API 或自建 Endpoint | **模型卡授權各異**；勿假設可商用 | https://huggingface.co/docs/api-inference |
| **AssemblyAI** | **不適用**（僅說話人 diarization／轉錄，非 stem） | — | — | — | — | — | — |
| **騰訊雲 數據萬象 CI「人聲分離」** | 人聲／背景；可配 Bass、Drum 等（COS 任務） | 中國區雲 | **0.08 元／分鐘**（按輸出時長；屬「音訊智能處理」） | 需 COS；與國內產品整合佳 | 中：COS + CI 任務 API | 騰訊雲商用條款 | https://cloud.tencent.com/document/product/460/81777 · https://cloud.tencent.com/document/product/460/58433 |
| **火山引擎 音源分離** | 音源分離（人聲／伴奏類） | 中國區雲 | 免費 **100 分鐘／開通 3 個月內**；後付費 **0.20／0.18／0.16 元／分鐘**（階梯）；次數包可買 | 併發預設有限（文件寫 10；可增購） | 中：火山 OpenAPI | 字節跳動雲商用條款 | https://docs.volcengine.com/docs/audio-technology/product-billing-4 |
| **阿里雲 MPS／IMS MusicDemix** | 人聲 + 伴奏 | 中國區雲 | 公開頁可見約 **0.1 元／分（MPS 視頻 AI）** 或 **0.2 元／分（IMS 智能生產）**（地域／產品線不同，**接入前再核對計費項**） | 與阿里雲媒體鏈整合 | 中：MPS／IMS 任務 | 阿里雲商用條款 | https://help.aliyun.com/zh/ims/user-guide/audio-and-video-intelligent-production-overview |

### LALAL API 是否給 indie／開發者？（已核對）

**是，不必先走 Enterprise 業務銷售。**

依據：
- 定價 FAQ：Pro 適合需要 **API access** 的使用者。  
- 第三方整理的官方 llms／OpenAPI 說明（apis.io，2026-08）：**「API access is available with the Pro plan or any minute top-up pack — no subscription required」**；Starter 無 API。  
- FAQ：帳號 **activation key** = 桌面端啟用與 **API** 憑證（header `X-License-Key`）。  
- 另有 Business／Enterprise（無限分鐘、10GB、batch、SLA）給規模化／白牌，但 **公有 API v1 文件與 Python 範例已公開**。

注意：LALAL **按 stem 類型數乘時長扣分鐘**；若一次要 4 stems，成本可 ≈ 4× 僅人聲+伴奏。

---

## 二、自架／開源模型

| 選項 | Stems | 託管 | 成本 | 延遲／品質 | 整合 | 授權注意 | 參考 |
|------|-------|------|------|------------|------|----------|------|
| **Demucs** `htdemucs`／`htdemucs_ft` | 4（v/d/b/o）；`--two-stems=vocals` → vocals+no_vocals；`htdemucs_6s` 加吉他／鋼琴 | 自架 GPU／CPU | GPU 機時；CPU 慢 | `ft` 更好但約 4× 慢；教育用標準 | 與現有 MVP **已對接** | **程式碼 MIT**；**預訓練權重**社群長期標為研究／訓練資料（MUSDB）限制 → **產品商用前需法務／改用明確可商用權重或授權 API** | https://github.com/facebookresearch/demucs |
| **UVR／MDX-Net** | 人聲／伴奏等（GUI／CLI 生態） | 自架 | GPU | 部分檢查點人聲極強 | 整合偏雜（多檢查點） | **權重授權常不明／研究向** | UVR 社群／HF mirrors |
| **BS-RoFormer** | 多 stem（視檢查點） | 自架 | GPU | 新一代、常勝 Demucs 於某些榜 | 中高（需正確檢查點） | **架構程式可 MIT**；**預訓練權重≠自動可商用** | https://github.com/lucidrains/BS-RoFormer |
| **demucs-onnx（瀏覽器）** | vocals 專用或 4／6 stem ONNX | **瀏覽器 WASM**（音訊不離機） | 頻寬（模型 ~136–166MB fp16）+ 用戶 CPU | 桌機可近即時～亞即時；手機較慢；隱私佳 | 適合 PWA 靜態路徑 | ONNX 工具 MIT；**權重仍跟 Demucs 同源疑慮** | https://stemsplit.github.io/demucs-onnx/browser/ · https://github.com/StemSplit/demucs-onnx |
| **Spleeter**（legacy） | 2／4／5 stems | 自架 | CPU／GPU | **已過時**，品質遜於 Demucs／RoFormer | 易但不宜新品 | Deezer；MIT 程式，模型舊 | https://github.com/deezer/spleeter |

---

## 三、推薦路徑（MVP → 產品）

### A) 最快出貨、品質可控（託管 API）— **首選 StemSplit，備選 LALAL**

1. **StemSplit**：indie 友善、點數不過期、一次 job 拿 BOTH／4／6 stems、文件／SDK 清晰、免費 5 分鐘可驗。與「類 LALAL 教育站」對齊成本低。  
2. **LALAL.AI**：品牌與品質認知強；Pro 或 Top-up 即可拿 API key；**多 stem 會乘計費**，要算清楚。產品想「跟 LALAL 同級體驗」時很合適。  
3. Music AI：stem 種類多、教育場景契合，但 **每 stem module 分開計價**，workflow 設定稍重。

### B) 長期最低成本／教育批次（自架或開源）— **GPU 上 Demucs／後續 BS-RoFormer**

- 短期：延續現有 **Demucs `htdemucs` two-stems**（已在 app）。  
- 有 GPU（RunPod／Vast／自有）：佇列 worker 處理上傳。  
- **商用上線前**：釐清權重授權，或改走已授權的商業 API／自訓／明確可商用檢查點。  
- 瀏覽器 **demucs-onnx**：適合「隱私優先、零伺服器推論」Demo／輕量 PWA；大檔與手機體驗要測。

### C) 混合（建議產品路徑）

| 階段 | 做法 |
|------|------|
| MVP 驗收 | StemSplit API（或 Replicate Demucs）接上現有 UI；保留本機 Demucs／ffmpeg 作離線／開發 |
| 教育免費額度 | 短預覽用 demucs-onnx 瀏覽器 **或** 自架 CPU／小 GPU 配額 |
| 付費／高品質 | StemSplit BEST 或 LALAL Fast；中國用戶可加騰訊 CI／火山作區域備援 |
| 規模化 | 自架 GPU 叢集跑 Demucs／RoFormer（授權清完後），API 僅作 overflow |

**中國區**：若主力用戶在國內，優先評估 **騰訊雲人聲分離（0.08 元／分）** 或 **火山音源分離**（有免費額），延遲與合規較穩；國際品質旗艦仍可用 StemSplit／LALAL。

---

## 四、建議的下一步整合（對應現有 Flask／PWA）

### 路徑 A — StemSplit（建議先做）

1. 於 https://stemsplit.io 註冊，拿 API key，用 5 免費分鐘跑 1–2 首測人聲 SDR／聽感。  
2. 後端新增 `STEM_PROVIDER=stemsplit`：`POST /api/v1/upload` → PUT 檔 → `POST /api/v1/jobs`（`outputType: BOTH` 或 `FOUR_STEMS`）→ poll／webhook。  
3. **API key 只放伺服器**；PWA 只打自家後端。  
4. UI 進度改為 job `progress`；完成後轉存／簽名 URL 供下載。  
5. 記帳：按 `durationSeconds` 扣用戶額度（對齊教育免費分鐘）。

### 路徑 A′ — LALAL（若要品牌同級）

1. 開 Pro 或買 Top-up → Profile 取 activation key → `X-License-Key`。  
2. 依 https://www.lalal.ai/api/v1/docs/ 與官方 Python 範例：upload → split（先只選 vocal/instrumental）→ check → download。  
3. 產品若要多 stem，在 UI 明示「每多一種 stem 多扣分鐘」。

### 路徑 B — 自架強化

1. 部署 GPU worker（Docker + demucs）；Redis／資料庫佇列。  
2. 與現有 `app.py` 同一 job 介面，便於 A/B。  
3. 平行 PoC：`demucs-onnx` 靜態頁「本機分離」開關（隱私模式）。

### 路徑 C — 混合開關

環境變數例如：`SEPARATOR_BACKEND=stemsplit|lalal|demucs|ffmpeg`，依用戶方案路由。

---

## 五、不建議

- **AssemblyAI**：無 music stem separation。  
- **Spleeter**：僅作歷史參考，新品質基線勿用。  
- **瀏覽器直接呼叫任何商業 API key**：金鑰會外洩（LALAL CORS 甚至允許瀏覽器送 key——更危險）。  
- **未核權重授權就商用 Demucs／UVR／BS-RoFormer 權重**。

---

## 六、粗成本感（僅公開價可算者；4 分鐘歌、僅 vocals+instrumental）

| 後端 | 約略成本／曲 |
|------|----------------|
| StemSplit | ~$0.40–0.80（視方案；$0.10–0.20/min × 4） |
| Music AI | Instrumental $0.05×4 + Vocals $0.07×4 ≈ **$0.48**（若兩 module 都跑） |
| LALAL | 扣 **8 Fast 分鐘**（4 min × 2 types）；相對訂閱／Top-up 攤提 |
| 騰訊 CI | 0.08 元/分 × 輸出時長（見官方計費說明） |
| 火山 | 0.16–0.20 元/分 |
| Replicate Demucs | 常遠低於 $0.05–0.10／短曲（隨時長；頁面示例 ~$0.0062／短 run） |
| AudioShake | USD **unknown**（僅知 2 targets × 4 min × 1.0 credit） |


---

## 七、StemSplit 已整合至本專案（設定步驟）

程式已支援 `STEM_PROVIDER=stemsplit`／自動偵測金鑰。金鑰**只放伺服器環境變數**，勿寫進前端或 git。

```bash
# 1) https://stemsplit.io → Settings → API Keys
export STEMSPLIT_API_KEY="sk_live_xxxxxxxx"
# 可選
export STEM_PROVIDER=auto                 # 有 key 時自動選 stemsplit
export STEMSPLIT_BASE_URL=https://stemsplit.io
export STEMSPLIT_QUALITY=BALANCED         # FAST | BALANCED | BEST
export STEMSPLIT_OUTPUT_FORMAT=WAV

# 2) 重啟
cd /workspace/stem-splitter && ./start.sh

# 3) 健康檢查
curl -s http://127.0.0.1:8765/api/health
# 期望： "stemsplit_configured": true, "provider": "stemsplit"
```

伺服器代打流程：`POST /api/v1/upload` → PUT 檔案 → `POST /api/v1/jobs`（`outputType: BOTH`）→ poll → 下載 vocals／instrumental 到 `data/outputs/<uuid>/`，既有 UI 預覽／下載不變。

實作檔：`stemsplit_client.py`、`app.py`（`_run_stemsplit`）。無真實金鑰時可用 `tests/test_stemsplit_mock.py` 做 mock 驗證。
