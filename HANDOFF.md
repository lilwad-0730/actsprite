# ActSprite 交接文件（給接手的 Codex）

## 接手更新（2026-11-02）

以下更新優先於後面的 11/1 歷史快照；歷史快照中的待辦可能已完成，以本節與 Git 現況為準。

- **Demo V6：已驗證並經使用者驗收。** 成片 161.6 秒（2:41.6）、1920×1080、30 fps、4848 格。
  使用者已發布至 YouTube：[ActSprite Demo](https://youtu.be/4VDyiQ0EOP4)。已從 YouTube oEmbed 核對影片標題；
  本次沒有重看線上全片或驗證所有播放環境。本機影片為 `../Demo/ActSprite_Demo_v6.mp4`，字幕為
  `../Demo/ActSprite_Demo_v6_en.srt`；解碼、字幕順延、混音與使用者驗收紀錄在
  `out/_eval/demo/edit_v6_bookends/validation.json`。
- 影片統一使用另一次 knight/run 錄製成品：**16 格、20 fps、0.8 秒循環、13/16 通過**；
  來源資訊在 `out/_eval/demo/edit_v1/recorded_export_info.json`。不要混用下方較早驗收的 12/16 成品，
  也不要把歷史 E1 的 68 格、32%／79% 當成本次結果。片中仍保留畫風、比例、細節與像素化限制。
- End at 預設留白的修正已提交並部署（程式 commit `10110c6`）；後端仍以留白表示自動取段，
  從 Start at 起最多取 5 秒。README 中英文與 Space 說明已補上 Demo 入口和拍攝、表演、角色圖片 tips。
  Tips 是素材準備建議，沒有量測成提升通過率的數據。
- Demo 配樂 `insomnia.wav` 為使用者提供；真人錄影、配音、配樂與本機剪輯產出均不納入 Git。
- **交件尚未完成。** 最近核對 GitHub 儲存庫仍為 private；公開前檢查、使用者公開決定、匿名存取與下載驗證、
  正式提交表單及成功收據仍待處理。E2／E5 未執行，保持如實揭露。

- **下載成品的 Unity 驗收：已驗證。** 使用者於 2026-11-02 確認「實際操作與視覺效果已驗證完畢」。
  本次成品為從 Space 下載的 `actsprite_knight.zip`：run 16 格、20 fps、0.8 秒循環；已確認流暢度、腳底貼地與左右移動。
  這是較早的下載成品，生成評分仍是 12/16 格通過；人工驗收不會改寫分數。正式 Demo 使用上方另一次 13/16 成品。
- 驗收時修正兩項問題：Unity 匯入器移除多餘的結尾關鍵格，避免最後一格多停一次；Unity smoke test 用 `finally`
  還原物理模擬模式，避免測試後遺留 Script 模式，導致試玩角色浮空且無法移動。獨立驗收專案已恢復 FixedUpdate。
  Unity 回歸為 `SMOKE RESULT PASS`；下載成品的實際 Play Mode 自動檢查確認落地誤差約 -0.001 px、D/A 分別移動
  +2.4/-2.4 units、放開按鍵停止且保持貼地。證據在 `out/_eval/acceptance/downloaded/` 的
  `unity_import_result.txt`、`unity_play_result.txt`、`unity_regression.log`；這些本機產出不提交。
- 使用者已明確授權將本機變更 commit、push 並部署 Space；本次發布包含動作格數設定、Start/End、Name／免費改名、
  損壞 SAM 遮罩處理及手機旋轉資訊修正。`.claude/`、`.env`、真人影片及 `out/` 產出不提交。
- 網頁設定：idle 8 格／8 fps、walk/run 16 格／auto、jump 12 格／auto、attack 10 格／15 fps；SAM 最多取樣 30 fps。
  jump/attack 有 End 時用 span，沒填則找最劇烈片段。Start/End 無效時不扣追蹤次數。
- 本次文件更新與之前 End at 修正的 `tests/` 均為 128 項通過；較早包含額外實驗的 134 項結果是另一個測試範圍，不可混用。
  執行測試使用 `--basetemp out/_eval/acceptance/<全新資料夾>`，避開預設暫存目錄的權限問題。
  Demo 剪輯與本次文件更新未呼叫付費模型。
- 攻擊 10 格已實測：正確直式畫面僅 4/10 通過，US$0.947636；之前橫躺畫面的無效測試 US$0.750469 不列入品質比較。
  仍會把窄站姿畫成大跨步，網頁與說明均揭露此限制。不要把舊的 15 格測試或 E1 歷史數據當成本次發布的通過率。
- 本機 `logs/cost.csv` 最近核對累計 US$45.507254；本次 Unity 修正與驗收沒有呼叫付費模型。
  Space 使用另一份暫存花費紀錄，兩者不能當成同一份累計。
- 已建立獨立 Unity 驗收專案 `out/_eval/acceptance/UnityProject`；本次發布的匯入與動畫自動檢查為 `SMOKE RESULT PASS`，
  紀錄在 `out/_eval/acceptance/unity_release_smoke.log`。這不是使用者原本的遊戲專案，也不能替代人工畫面驗收。
- 驗收影片 `out/_eval/acceptance/01_upload_run_h264.mp4` 已轉 H.264／yuv420p，99 格、3.303 秒，Gradio 相容性與完整解碼通過。
  舊 MPEG-4 Part 2 編碼不適合瀏覽器預覽，不要再拿那份上傳。
- 舊線上版（8 格、15 fps）已用同一修正版影片、Start=0 實測 Track 成功：循環 0.67–1.47 秒。
  循環判定仍對取樣起點敏感；該成功紀錄不能當成新版 30 fps 的驗證。
- 使用者希望盡量減少人工介入：一般開發、技術測試、檔案整理由 Codex 接手，提供直接連結；帳號操作、付款及
  新的重大規格／公開發布授權才集中請使用者處理。不要反覆要求已授權的 commit／部署確認。
- 已完成線上下載成品到 Unity 播放的跑步案例驗收，以及 Demo V6 驗收與 YouTube 發布；正式提交尚未完成。

---

寫於 2026-11-01（台灣時間）。內容是到這一刻為止的狀態、還沒做完的事，以及討論過但還沒告訴使用者或還沒執行的想法。
開始前請先讀 `CLAUDE.md`（開發規則）和上一層資料夾的企劃書 `../ActSprite 參賽提案規劃書.md`（規格）。

**時程：** 功能凍結 11/1（已過），內部截止 **11/4 22:00**，官方截止 11/5 10:00（台灣時間）。

---

## 1. 必守規則（使用者明確要求過）

- 跟使用者用**繁體中文**溝通。
- **API 金鑰：** 只從 `.env` 的 `META_API_KEY` 讀取，絕不要求使用者在對話中貼出金鑰。
- **花費：**
  - 每次批次呼叫 Meta API 前先印出預估花費，實際花費自動寫入 `logs/cost.csv`。
  - 累計達 $140 立刻停止並回報。目前是 **$40.37**。
  - 單一決定預計超過 $5 先問使用者。
- **一定要先問使用者的情況：**
  - 改企劃書（`../ActSprite 參賽提案規劃書.md`）任何內容。
  - 改跟 Unity 共用的輸出格式（ZIP 結構 `actsprite_<name>/`、`<name>_sheet.png`、`<name>_meta.json` 欄位）。
  - 改寫已驗收的程式、刪檔、付款或密碼。
  - **部署 Hugging Face Space**（這是公開內容）。
  - **commit / push**（使用者說了才做）。
- **素材與隱私：**
  - 任何真人影片都要先取得出鏡者同意。
  - 有人臉的圖、使用者的影片、`out/` 產出都不進 git（`samples/*.mp4` 已被 ignore）。
  - 不要寫出畫線稿人物的女朋友的名字。README 的寫法「the girlfriend of the author」是使用者自己改的，不要動。
- **驗收與回報：**
  - Unity Play Mode、畫面好不好看由使用者驗收，不可自行標成完成。
  - 評估數字只能來自實際執行紀錄。
  - 回報狀態只用三種：已驗證（附證據）、已完成但未驗證、未完成。

---

## 2. Git 與部署狀態

### Git
- `main` 與 `origin/main` 同步，最新 commit 是 `7cb80c2`（評估 E1/E3/E4/E6）。
- 這個 commit 是另一個工作階段做的，它在 `eval/README.md` 提到「uniform-time sampling update」。如果取幀方式有改，請先看那份說明。

**本機還沒 commit 的改動**（使用者說**先不要部署也先不要 commit**，要等他決定）：

| 檔案 | 改了什麼 |
| --- | --- |
| `actsprite/config.py` | `DEMO_RECIPES`：網頁版依動作套用設定，見下表；`DEMO_SAM_FPS` 15 → 30（16 格需要更細的取樣） |
| `app.py` | 1. 依動作套用設定<br>2. 新增「End at」結束時間欄位（jump/attack 填了就取開始到結束整段，用 span 模式）<br>3. 新增「Name」欄位與免費「Rename the ZIP」（`actsprite_<name>.zip`，名稱只留英數字、`-`、`_`，最多 32 字）<br>4. 鎖定的進階設定欄位改成顯示每個動作的設定 |
| `actsprite/capture.py` | SAM 遮罩解不開（`InvalidSegmentationMaskError`）時跳過該格，不再整個追蹤當掉（11/1 網頁版跳躍實測遇到） |
| `tests/test_capture.py` | 上面這個修正的測試 |
| `scripts/unity_smoke/` | Unity 匯入工具的自動檢查（原本只放在暫存資料夾），用法見該資料夾的 README |
| `scripts/web_steps_test.py` | 不開伺服器、直接在程式內跑網頁三步驟的測試腳本 |
| `HANDOFF.md` | 本文件 |
| `.claude/launch.json` | 本機預覽伺服器設定，**不要 commit** |

網頁版依動作的設定（使用者 11/1 核准的 A 方案）：

| 動作 | 格數 | 播放速度 | 取哪一段 |
| --- | --- | --- | --- |
| idle | 8 | 8 fps | 自動找循環 |
| walk / run | 16 | 照影片速度（auto） | 自動找一步 |
| jump | 12 | auto | 有 End at：開始到結束整段；沒有：自動挑最劇烈的一段（會切掉頭尾） |
| attack | 10 | 15 fps | 同 jump；不固定雙腳（15 格加雙腳固定實測只有 2/15 通過，使用者改回這個） |

本機實測（騎士，透過 `scripts/web_steps_test.py`）：

| 動作 | 通過 | 花費 | 備註 |
| --- | --- | --- | --- |
| jump 1.73–3.0 s | 7/12 | $0.80 | 效果好；三步各 28 s / 83 s / 178 s |
| run | 9/16 | $1.58 | 有幾格不一致，費用約 8 格的 3 倍 |
| attack（舊設定 15 格、雙腳固定） | 2/15 | $1.80 | 效果很差 |

attack 改回 10 格之後還**沒有實測過**。

### Hugging Face Space
- 網址：https://huggingface.co/spaces/Andy0730huggin/actsprite
- 線上版本是 `7cb80c2` 的程式，**不含**上表任何本機改動。每人每天 2 次產出、5 次追蹤。
- 部署：`.venv\Scripts\python scripts/deploy_space.py`，會上傳**工作目錄**的檔案，包含沒 commit 的改動。
  - 只想部署已 commit 的版本時：`git worktree add --detach <暫存路徑> HEAD`，在那份副本裡執行部署腳本，再 `git worktree remove`。
  - 使用者已在本機登入 `hf auth login`。
- Space 用的是另一把 API 金鑰（Space secret），花費紀錄在 Space 的暫存空間，**Space 重啟就歸零**，所以 $40 上限不是真的累計上限。每日次數也存在記憶體，重啟會歸零。
- **改完網頁要同步更新：**
  - `README.md` / `README.zh-TW.md` 的 Web app 段落：目前寫「8 frames」和 8 格版本的實測時間。
  - `space/README.md`（Space 說明卡）。

### 企劃書（repo 外）
- 11/1 經使用者同意，改了第 94 行（每個動作的格數：網頁 idle 8、walk/run 16、jump 12、attack 10）和第 99 行（播放速度）。
- 改之前的版本備份在 Claude 的暫存資料夾，可能已被清掉。
- **還沒對齊的地方**（要改先問使用者）：
  - `../actsprite-context/actsprite-context/docs/02_product_spec.md` 還寫「公開 Demo 版：幀數 ≤ 8」。
  - 企劃書第 498 行寫「每天最多 8 次」，實際是每人每天 2 次。

---

## 3. 等使用者驗收或決定的事

1. **本機網頁改動要不要部署與 commit**（第 2 節那張表）。部署前建議先跑一次 attack 10 格的實測。
2. **Unity Play Mode 驗收**，在使用者的專案 `../unity test/actsprite`：
   - 騎士：新跳躍（落地蹲下）、連跳兩下（11/1 修過）、punch 攻擊（15 格，從 0 起算的第 3、4 格是手動複製第 2 格，報告裡有註明）、大小與跳躍速度（Scale 1.1859、Jump Speed 10.5，11/1 手動補回）。
   - lineman：20 格跑步。lineman 沒有 idle，站著時停在 `run_00`；也沒有跳躍。
   - 按 Tab 換角色後碰撞正常（開發指引第 3 階段的完成條件）。
   - 用 Import ZIP 匯入 `examples/` 的範例 ZIP，評審會走這個流程。
   - 使用者回報過兩個問題，都已處理：連跳卡在站姿（已修）、選單出現兩個「ActSprite」（第二個是使用者專案自己的測試腳本，已移到 Tools > Dungeon Knight Test）。
3. **網頁實測**（第 4 階段的完成條件：手機影片 → 網頁 → 下載 ZIP → Unity 按 Play 全程走通）。完整檢查清單在對話紀錄裡，重點是：
   - 手機操作、上傳自己的設計、錯誤訊息、每日上限、兩人同時使用不會互相混到、一小時後過期。

---

## 4. 下一步（依優先序）

### P0：交件前一定要做（11/4 22:00 前）
1. 使用者同意後，部署本機網頁改動，並更新兩份 README 的 Web app 段落和 `space/README.md`，再 commit。
2. **第 6 階段文件與發布：**
   - Demo 影片腳本：企劃書第 398–410 行有分鏡，旁白要配合實際功能改寫。第 406 行寫「評審標記第 5 幀並重生」，網頁版**沒有**逐格重畫功能，要改腳本或補功能。
   - X 貼文草稿：企劃書第 457 行附近。
   - README 最後檢查：「黑客松期間新增」清單、Credits、數字都要有出處。
   - 交件清單：企劃書第 515–540 行附近。
3. **repo 公開：** 目前是 private，使用者會在交件前自己切成公開。之後要用**沒登入的瀏覽器**確認 repo 頁面、README 裡的 `examples/*.zip` raw 下載連結和 `examples/previews/*.gif` 都打得開。11/4 如果還是 private 要提醒使用者。
4. **評估：** E2（跟手動在 Unity 做比花多少時間）需要使用者提供自己手動做的分鐘數；E5（SAM 遮罩對比手繪輪廓）沒跑。兩項在 `eval/README.md` 都標成未執行。

### P1：討論過但還沒做，或還沒跟使用者提的想法（做之前都要先問）
1. **跳躍分成「空中」和「落地」兩段播：** 目前 Unity 落地後才把整段跳躍播完。如果角色從高處落下、空中時間比動畫的空中段長，落地蹲下的格子會在空中先播掉，最後停在站直的姿勢。要徹底解決，需要在 `<name>_meta.json` 加上「落地從第幾格開始」，這會改到共用的輸出格式，要使用者同意。
2. **網頁逐格修正**（規格 §5.1）：重畫某一格並附一句指示、鎖定、刪除。網頁目前只能整組重來。
3. **重畫時避開快取：** 相同請求會直接用快取，所以重跑時壞掉的格子會原樣再出現（lineman 跑步就是這樣，最後只能改用影片裡另一步）。可以加一個選項，例如 `--fresh-frames 4,5`，在請求裡帶一個不影響畫面的變數，讓指定的格子重新畫。
4. **自動停損**（規格 §5.2）：前 3 格都沒過就暫停；花費超過預估 2 倍就暫停詢問。都還沒做。
5. **品質模式**（規格 §6：快速 / 標準 / 精細）和**驗證嚴格度**：指令列也還沒有這些選項。網頁的鎖定欄位只放了指令列真的有的選項，因為說明文字寫了「每個選項指令列都能用」。
6. **網頁用文字描述產生角色：** 指令列已有 `--description`，網頁還沒有。
7. **用指令列成果展示自由度（使用者提過的 C 方案，還沒做）：** 在 Showcase、README、Demo 影片放 48 格雙人舞（`out/knight_dance2_whole`）、正面視角加轉頭（`out/knight_dance_head`）、20 格跑步、整段跳躍等成果。
8. **補齊角色動作：** lineman 補 idle（可用 `samples/idle (1).MOV`）和 jump；hound 只有 walk。
9. **真正的 Space 花費上限：** 請使用者在 Meta 帳號替 Space 的金鑰設花費上限，或改用 Hugging Face 的持久儲存空間（要付費）。
10. **高度跟隨**目前沒套用在 walk / run（`config.HEIGHT_FOLLOW_MODES`）。
11. **攻擊站姿：** Muse Image 畫出拳時常變成大跨步，跟真人的窄站姿不一致。可以試在重畫提示裡加站姿描述，或用 `--feet-planted` 搭配一張站姿正確的第 0 格。
12. **手機版排版：** Showcase 的格子條固定高度，在窄螢幕上會被壓扁。

---

## 5. 技術筆記

**環境與執行**
- **本機跑網頁會被花費上限擋下：** 本機的 `logs/cost.csv` 已累計 $40.37，超過網頁版的 `DEMO_SPEND_CAP_USD = 40`，所以本機直接跑 `app.py` 任何付費步驟都會被拒絕。`scripts/web_steps_test.py` 會在執行時把上限暫時拉到 $140。
- 從暫存資料夾執行的腳本要加 `PYTHONPATH=.`；會用到流程的腳本要包在 `if __name__ == "__main__":` 裡，否則多行程解碼會失敗並退回單一行程，變得很慢。
- 測試：`.venv\Scripts\python -m pytest -q`，目前 103 個全過。

**流程**
- **快取：** 相同請求不重付錢，也不會變。想要不同的畫法，要換開始時間或關鍵格。
- **流程拆成三段：** `pipeline.plan_action`（追蹤、選格、姿勢線稿、角色圖）→ `draw_first_frame` → `finish_action`；`run_action` 就是三段串起來。網頁用這三段當三個檢查點。
- **模式：** 依動作自動選，`sequence.ACTION_MODES`：idle 用 loop，walk/run 用 gait，jump/attack 用 once。
  - once 會自動挑動作最劇烈的一段，常切掉頭尾。要完整動作就用 `--mode span --start --end`。
  - span 會關掉 idle 的「雙腳維持站姿」檢查，所以 **idle 不要用 span**。
- **畫面邊緣：** 手機影片的腳常碰到畫面底部，要加 `--edges left,right`。網頁版第 1 步失敗時會自動放寬再試一次。
- **影片取樣：** 每秒送給 SAM 的格數要夠，`--sample-fps 30` 才選得出 16–20 格。
- **內容審查：** Muse Image 擋下某次重畫時（HTTP 400 content filter），程式會保留目前最好的一張；第一次畫就被擋時會停下並提示換一段影片。
- **手動換格：** 騎士 punch 的第 3、4 格是手動複製第 2 格，記在該動作 `result.json` 的 `hand_edits`，`summary.md` 和 `scores.csv` 會顯示，評估時算未通過。

**Unity**
- 套件 `unity/ActSpriteImporter`，使用者的專案用本機資料夾引用（`file:`），改了程式切回 Unity 就會重新編譯。
- 重建 prefab 時會保留 Scale、Move Speed、Jump Speed、Read Keyboard。
- 套件內附的騎士在 `DemoCharacter/`，只在第一次 Build Demo Scene 時匯入。內附騎士更新後，使用者的專案要刪掉舊資料夾，或直接把新的 json 和 png 複製過去讓它自動重建。

**輸出資料夾**（git-ignored）
- `out/knight`：已驗收的騎士（idle、run、jump 12 格、attack 是 punch 15 格），備份在 `out/knight_before_jump`、`out/knight_before_height`。
- `out/lineman`：run 20 格加 attack，備份在 `out/lineman_before_run`。
- 其他 `out/*` 是試驗紀錄。

**範例 ZIP**（`examples/`）
- knight：只有 dance（48 格）。README 範例表格在 `f78f92c` 加了騎士跳躍的 GIF，但 ZIP 裡沒有 jump，要問使用者是把 jump 加進 ZIP，還是改表格文字。
- hound：walk。
- lineman：run 加 attack。
- `tests/test_examples.py` 會依輸出格式檢查這些 ZIP。

**其他**
- 背景與互動脈絡在 Claude 的記憶檔，交接後以本文件為準。
