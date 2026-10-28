# ActSprite — Claude Code 開發指引

## 1. 專案目標
- 參加 Meta Global AI Developer Hackathon：Indie Developer 賽道、Build for Your World 主題。
- 產品流程：手機影片 → SAM 3.1 追蹤 → 腳底對齊 → Muse Image 時間錨定重繪 → Muse Spark 1.3 與 SAM 3.1 驗證 → Sprite Sheet + JSON → Unity 可播放。
- 規格以「ActSprite 參賽提案規劃書」（repo 外，`../ActSprite 參賽提案規劃書.md`）為準；與本檔衝突時先問使用者。
- 時程（台灣時間）：功能凍結 2026-11-01；內部截止 2026-11-04 22:00；官方截止 2026-11-05 10:00。

## 2. 比賽規則對程式的硬性限制
- Repo 公開；只能提交 2026-10-26 之後新寫的內容，README 必須列出「黑客松期間新增」清單。
- 不得使用來源或授權不明的程式碼、資料、素材；新增套件前確認授權並記入 README 的 Credits。
- LayrKits/Sprite-Pipeline 與 Unity-Batch-Slice-Sprites 只參考做法，不複製任何程式碼。
- 主流程必須實際呼叫至少 3 個 Meta 模型（SAM 3.1、Muse Image、Muse Spark 1.3）。
- 提示詞與素材不得出現既有作品、角色或商標名稱。

## 3. 分工
- Claude Code：細部設計、程式、測試、評估腳本、README、影片腳本與發文草稿。
- 使用者：金鑰與付款、拍攝素材、Unity Play Mode 驗收、錄影、發文、提交、每個關卡的去留決定。
- 絕不要求使用者在對話中貼出 API Key；只請使用者自行填入 .env 後回覆「已設定」。

## 4. 環境
- Windows + PowerShell；Python 3.11，虛擬環境 .venv；Unity 6。
- 金鑰只從環境變數 META_API_KEY 讀取（由 `.env` 載入）。
- 每次批次呼叫 Meta API 前先印出預估花費；實際花費寫入 logs/cost.csv；累計達 $140 立即停止並回報。

## 4.1 已確認的 Meta Model API 事實（2026-10-28 讀官方文件 dev.meta.ai/docs）
- Base URL `https://api.meta.ai/v1`，Bearer key，OpenAI SDK 相容。
- SAM 3.1：模型 `sam-3.1`，`POST /v1/responses`；一個 `input_text`（短名詞片語）＋一個 `input_image` 或 `input_video`（`video_url` 可為 base64 data URL，或 `file_id`）。
  輸出在 `output_text`，每幀一行 `<Nf>id<|box;...|><|mask;x=0;y=0;data=H,W,<enc>payload|>`。
  遮罩是 box 範圍內的裁切（H×W 等於 box 大小）。用官方 `meta-sam-parser`（SAM License）解析。
  價格：圖片 $2.50 / 1000 張；影片 $0.20 / 1000 幀，每次至少計 50 幀。影片僅 MP4/MOV（H.264/H.265/MPEG-4）。
  實測（10/28）：SAM 影片呼叫本身很快（489 幀 25 秒），但 `meta-sam-parser` 的遮罩解碼是純 Python 逐像素，
  且解析時會先驗證解碼一次：480p 每幀約 3 秒 CPU、720p 約 6–7 秒。所以送 SAM 前先降到 480p、必要時降 fps，
  並用 `capture.parse_sam_output(workers=...)` 多行程解析。
- Muse Image：模型 `muse-image-1.0`，$0.01/張。Responses API 可交錯傳多張參考圖；
  `tools=[{"type":"image_generation", ...}]` 可關閉 web/image search 與 shell、設定 size（只決定比例）、`output_format`。
  背景永遠不透明 → 必須白底＋SAM 去背。編輯最多 10 張參考圖。
- Muse Spark 1.3：模型 `muse-spark-1.3`，輸入 $1.25 / 輸出 $4.25 每百萬 token；Contributor 版 `muse-spark-1.3-contributor` 會拿資料訓練，僅限使用者自拍素材。

## 5. 開發階段與完成定義
| 階段 | 日期 | 產出 | 完成定義 | 誰驗收 |
| --- | --- | --- | --- | --- |
| 0 可行性驗證 | 10/28 | spikes/ 腳本與 spikes/REPORT.md | 測試 A–D 皆有實測數字，附 Go 或備案建議 | 使用者決定去留 |
| 1 擷取與對齊 | 10/29 | capture.py、align.py | 範例影片輸出 8 張對齊 PNG 與姿勢線稿；pytest 全過；附預覽圖 | Claude 測試＋使用者目測 |
| 2 重繪與驗證 | 10/30 | restyle.py、verify.py、pack.py | 一個指令產出 Sprite Sheet、JSON、逐幀分數 CSV；門檻已用實測資料校準 | Claude 測試＋使用者目測 |
| 3 Unity | 10/31 | 匯入工具、Demo 場景 | 動畫循環無跳格、腳底貼地、換角色後碰撞正常 | 使用者在 Play Mode 確認 |
| 4 網頁與部署 | 11/1 | app.py、Hugging Face Space | 手機影片到 Unity 按 Play 全程走通；花費上限與次數限制生效 | 使用者實測 |
| 5 評估 | 11/2 | eval/ 腳本、CSV、圖表 | E1–E4 數字全部來自實際執行紀錄 | Claude＋使用者核對 |
| 6 文件與發布 | 11/2–11/4 | README、影片腳本、X 文案 | README 完成、commit、push，並確認遠端 repo 在無痕視窗可開啟 | 使用者確認 |

## 6. 每次修改的工作規則
- 先讀相關檔案並說明打算改什麼，再動手；最小修改，保留既有行為。
- 每個階段一組清楚的 commit；commit 訊息寫明做了什麼。
- 不新增非必要依賴；新增前說明理由與授權。
- 中斷後從現有狀態續做，不重寫已通過驗收的部分。

## 7. 程式碼檢查清單（每次 commit 前自查）
- [ ] 無硬編碼金鑰；.env 未被追蹤；已跑憑證掃描（gitleaks，未安裝則用 git grep 搜尋 key、token、secret）
- [ ] 每個 API 呼叫都有 timeout、重試上限、快取（相同輸入不重複付費）與花費紀錄
- [ ] 門檻與權重只放在 config.py
- [ ] 函式有型別註記；錯誤訊息說明如何修正
- [ ] 新增或修改的邏輯有單元測試，pytest 全過
- [ ] 大型影片與產出不進 git（samples/ 的示範素材除外）
- [ ] 新套件已記入 README Credits 與授權
- [ ] 實際執行過一次並附輸出，不以「應該可以跑」代替

## 8. 驗收與回報規則
- 狀態只用三種：已驗證（附證據：指令輸出、截圖路徑、數據檔）、已完成但未驗證、未完成。
- 需要 GUI 或人工判斷的項目（Unity Play Mode、畫面一致性目測、影片品質）一律標「待使用者驗收」，不得自行標為完成。
- 評估數字只能來自實際執行的紀錄檔；不得估算、補值或美化。
- 每天結束時回報：今日完成、驗證證據、未完成與原因、累計花費、需要使用者做的事、明日計畫。

## 9. 需要向使用者索取的資料
| 資料 | 何時 | 形式 | 用途 |
| --- | --- | --- | --- |
| Meta API Key 已設定 | 階段 0 開始前 | 使用者自填 .env，回覆「已設定」 | 呼叫 API |
| 測試影片 3 段（跑、跳、寵物或玩偶） | 階段 0 | MP4、3–5 秒，放 samples/ | 可行性測試與開發 |
| 出鏡者同意確認 | 使用任何真人影片前 | 文字確認 | 合規 |
| office hours 的回答 | 10/29 前 | 貼回對話 | 調整設計 |
| Day 1 去留決定 | 階段 0 結束 | Go、備案 A 或備案 B | 決定方向 |
| Baseten、Modal 額度結果 | 10/30 | 有或沒有 | 決定是否角逐 Open Weight 獎 |
| Unity 專案路徑與版本 | 階段 3 前 | 路徑 | 放置匯入工具 |
| Play Mode 驗收結果 | 階段 3、4 | 三項各自通過與否＋截圖或錄影 | 驗收 |
| Hugging Face Space 網址（Secrets 由使用者設定） | 階段 4 前 | 網址 | 部署 |
| 手動流程計時 | 階段 5 | 分鐘數 | E2 基準 |
| Demo 影片與 X 貼文連結 | 11/3 | 網址 | README 與提交 |

已取得：GitHub repo `https://github.com/lilwad-0730/actsprite`；第一個角色＝像素風騎士。

## 9.1 Day 1 決定（2026-10-28，使用者核准 Go）
細節與數據見 `spikes/REPORT.md`。以下取代規劃書中對應的做法：
1. 姿勢驗證＝SAM 剪影 IoU（統一身高、腳底對齊、容差 px）＋ Muse Spark 姿勢分數；姿勢分數與身分分數在同一次評審呼叫取得。
2. 角色設定圖：正常頭身、不加披風或長斗篷等大面積飄動物件。
3. 去背：白底灌水法（`restyle.white_flood_cutout`）；SAM 只用於擷取與姿勢驗證。
4. 像素風：模型畫乾淨插畫，程式縮小並套統一調色盤（`pack.pixelate`）。

## 10. 必須停下來詢問的情況
- 任何需要付款、輸入密碼或金鑰的步驟。
- 規格不明、設計衝突，或實測結果與門檻差距大而需要改方向。
- 單一決定預計花費超過 $5。
- 需要刪除檔案，或改寫已通過驗收的程式。
- 本檔、規劃書與官方文件或實測結果互相矛盾。
