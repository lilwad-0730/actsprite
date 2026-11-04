# ActSprite — 演出動作，直接遊玩

[![English](https://img.shields.io/badge/Language-English-lightgrey)](README.md)

> 黑客松：Meta Global AI Developer Hackathon · 賽道：Indie Developer · 主題：**Build for Your World**

用手機演出一個動作，取得角色一致、可直接在 Unity 使用的遊戲動畫。
8–12 幀的動作從影片到可匯入 Unity 的 ZIP 約需 4–6 分鐘、Meta API 費用約 US$0.5–1（[實測數據](#評估)）。

**狀態：** 黑客松原型。已用 knight/run 案例走通網頁追蹤、生成、下載 ZIP 到 Unity 播放的流程，
並人工驗收動畫播放、腳底貼地與 A/D 左右移動。

畫風提醒：預設的 `pixel` 風格會將最終 Sprite 像素化，自己上傳的角色也一樣；生成前請先看[像素化與原作保真限制](#像素化與原作保真限制)。

## Demo

[觀看 YouTube 示範影片（2 分 42 秒）](https://youtu.be/4VDyiQ0EOP4) ·
[試用線上版](https://andy0730huggin-actsprite.hf.space)

影片展示角色選擇與自訂設計上傳、追蹤、第一幀檢查、驗證重畫、ZIP 下載與 Unity 匯入。
片中的 knight/run 成品為 **16 格、20 fps**，循環長度 0.8 秒；**13/16 格通過自動檢查**。
這是單次錄製案例的結果，不代表所有影片的準確率；最終動畫仍需要人工美術檢視。

拍攝或上傳前，可先閱讀[讓產出更好的實用技巧](#讓產出更好的實用技巧)。

## 評審：兩分鐘內完成驗證（不需要 API Key）

**1. 查看完成的輸出。** 每個 ZIP 都是處理流程實際交付給 Unity 的內容：

| 像素騎士：ZIP 內為舞蹈（正面、48 幀）；跳躍（12 幀）為預覽 | 像素獵犬：行走 | 線稿人物：跑步（20 幀）與攻擊 |
| --- | --- | --- |
| ![騎士舞蹈](examples/previews/knight_dance.gif) ![騎士跳躍](examples/previews/knight_jump.gif) | ![獵犬](examples/previews/hound_walk.gif) | ![線稿人物跑步](examples/previews/lineman_run.gif) ![線稿人物攻擊](examples/previews/lineman_attack.gif) |
| [下載 ZIP](https://github.com/lilwad-0730/actsprite/raw/main/examples/actsprite_knight.zip) | [下載 ZIP](https://github.com/lilwad-0730/actsprite/raw/main/examples/actsprite_hound.zip) | [下載 ZIP](https://github.com/lilwad-0730/actsprite/raw/main/examples/actsprite_lineman.zip) |
| 舞蹈：48 幀中有 40 幀通過全部檢查 | 10 幀中有 4 幀 | 跑步 20 幀中有 16 幀，攻擊 10 幀中有 6 幀 |
| 舞蹈：Meta API 呼叫費用 US$3.07 | US$1.01 | US$1.21 + US$0.53 |

騎士 ZIP 只包含舞蹈。跳躍 GIF 是 Unity 匯入工具內附的騎士（`unity/ActSpriteImporter/DemoCharacter`：待機、跑步、跳躍、攻擊），執行 **ActSprite > Build Demo Scene** 時會自動匯入。

每個 ZIP 內含 Sprite Sheet、供 Unity 匯入工具使用的 `<name>_meta.json`、每一幀的 PNG、GIF
預覽，以及記錄每次重繪分數的 `report/scores.csv`（`needs_review` 代表該幀未通過所有檢查）。
費用是 `logs/cost.csv` 中每個 ZIP 背後所有付費呼叫的總和，包含 SAM 3.1 影片追蹤、角色設定圖，
以及每次重繪與檢查。10 幀的動作約需 4–6 分鐘（量測結果見 `spikes/REPORT.md`），48 幀的舞蹈約 15 分鐘。
獵犬和線稿人物的 ZIP 於 10/31 以 10 幀、15 fps 重新製作；費用只計新送出的呼叫（SAM 3.1 追蹤與部分重繪來自快取）。線稿人物的跑步於 11/1 以 20 幀、20 fps 加入。

**2. 執行測試。** 不需要金鑰或網路；`tests/test_examples.py` 會依輸出合約檢查三個 ZIP。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest
```

## 像素化與原作保真限制

**像素化是 `pixel` 風格刻意採用的輸出處理。** 上傳自己的角色，不代表系統會原樣保留其畫風：
**My own design → Output style** 同樣預設為 `pixel`。即使原圖本來就是像素畫，也會重新生成並取樣到
ActSprite 的固定格線，不能原封不動保留原圖的像素排列。

### 像素風角色會經過哪些處理？

1. Muse Image 依角色參考圖與姿勢線稿重繪。`pixel` 的提示詞要求乾淨、平塗的插畫；模型產生的圖還不是最終 Sprite。
2. 程式去背、對齊各幀，再將每格縮到 **64 × 64**，並將顏色對應到從角色參考圖取得、**最多 24 色的共用調色盤**。
3. 每個像素以清晰的 2 × 2 方塊放大，輸出為 **128 × 128** 的透明 PNG 與 Sprite Sheet。
   放大檔案尺寸不會補回在 64 × 64 階段遺失的細節。

網頁的第一幀預覽顯示的是這些輸出處理之前的模型圖片。請以最後的動畫預覽、逐格圖與下載 PNG，
判斷實際放進 Unity 的外觀。

### 為什麼採用這個做法？

- **統一每幀的像素顆粒。** 早期實驗中，直接要求模型畫像素風，有時得到的仍是高解析插畫。
  因此改由程式套用固定格線，讓每幀都有相同的像素尺度，降低對模型每次都畫出一致顆粒的依賴。
- **減少顏色在幀間變動。** 模型每次重畫，可能產生稍有差異的綠色、陰影或衣服顏色。
  對應到同一組參考調色盤，有助於減少這類色彩變化；它無法修正錯誤姿勢、缺少配件或角色走樣。
- **提供一致的小尺寸遊戲 Sprite。** 固定格線與輸出尺寸，讓角色在遊戲中以小尺寸顯示時維持一致的像素外觀。
  代價是犧牲細節，因此這項設計不能當作忠實重現原作的保證。

細輪廓、手指、眼睛、衣服花紋與柔和陰影，可能合併、變色或消失。即使不做像素化，AI 重繪也可能改變比例、材質與線條。

### 哪些選擇會被像素化？

| 角色／所選風格 | 輸出像素化 | 每格 PNG 尺寸 |
| --- | --- | --- |
| Pixel knight／Hound（`pixel`） | 會：64 × 64 格線與共用調色盤 | 128 × 128 |
| My own design 選 `pixel`（預設） | 會，自己上傳的插畫與像素畫也會套用 | 128 × 128 |
| Line-art man，或 My own design 選 `handdrawn`、`lineart`、`ink` | 不額外套像素格線與限色；仍會縮放以符合輸出尺寸 | 256 × 256 |

若不希望輸出被額外像素化，請在 **1. Track 之前**選擇 **My own design → Output style → handdrawn**，
或選擇 `lineart`／`ink`。指令列則使用自己的 `--sheet`，搭配 `--style handdrawn` 或其他非像素風格。
網頁上若在追蹤完成後才改選項，需要重新追蹤才會套用。

**不做像素化，不等於完整保留原畫風。** 例如 `handdrawn` 仍要求乾淨墨線與平塗陰影，`lineart` 則要求不填色的鉛筆線稿。
參考圖會引導生成結果，但兩者都不能保證完整保留原作筆觸、漸層、比例與每一處細節。
請先檢查第一幀，再決定是否生成其餘格子，完成後也要檢查最終輸出。

設計背景見[早期實驗紀錄](spikes/REPORT.md)；目前實作見[風格設定](actsprite/restyle.py)與[輸出處理](actsprite/pack.py)。

## 運作方式

```mermaid
flowchart LR
    A["手機影片"] --> B["SAM 3.1 追蹤表演者"]
    B --> C["關鍵幀轉成灰色姿勢線稿"]
    C --> E["Muse Image 依角色重畫每個姿勢：先畫第 0 幀，其餘以它為錨點"]
    E --> F{"Muse Spark 1.3 評審＋SAM 3.1 剪影檢查"}
    F -- "未通過：帶評審的修改意見重畫，最多 2 次" --> E
    F -- "通過" --> G["腳底對齊、統一調色盤：Sprite Sheet＋JSON"]
    G --> H["Unity 匯入工具：動畫、Animator、Prefab"]
```

| 步驟 | Meta 模型 | 工作 |
| --- | --- | --- |
| 擷取 | SAM 3.1（`sam-3.1`） | 追蹤影片中的表演者，取得每幀的像素遮罩 |
| 重繪 | Muse Image（`muse-image-1.0`） | 依角色重繪每個姿勢，後續各幀以已核准的第一幀為錨點並行繪製 |
| 驗證 | Muse Spark 1.3（`muse-spark-1.3`）＋SAM 3.1 | 評審評分姿勢與角色一致性；SAM 再次檢查剪影 |

## 快速開始（開發環境）

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env   # 接著將 Meta Model API Key 填入 .env
.venv\Scripts\python -m pytest
```

## 每個動作只需一行指令

```powershell
.venv\Scripts\python -m actsprite samples/attack.MOV --action attack --edges left,right             # 像素騎士
.venv\Scripts\python -m actsprite samples/pet.mp4 --action walk --actor dog --character hound         # 像素獵犬
.venv\Scripts\python -m actsprite my_jump.mp4 --action jump --sheet my_hero.png --style lineart --name hero
.venv\Scripts\python -m actsprite dance.mp4 --action dance --mode span --view front --frames 48 --edges top,bottom,left
```

每次執行都會使用 SAM 3.1 追蹤主角、依動作設定平均取樣關鍵幀（跳躍／攻擊取一個爆發動作，待機取一個循環，
行走／跑步取兩步步態）、繪製姿勢導引、以 Muse Image 將每幀重繪成指定角色，並進行檢查
（SAM 3.1 剪影、Muse Spark 1.3 評審、調色盤與腿部動作）。未通過的幀最多重繪兩次。
第 0 幀以外的各幀會並行繪製，並以已核准的第 0 幀作為錨點。結果會新增為
`out/<name>/actsprite_<name>.zip` 中的一列：

```
actsprite_<name>/
  <name>_sheet.png                 每個動作一列、固定格子（像素風 128 px，其他風格 256 px）
  <name>_meta.json                 格子大小、腳底軸心（0.5, 0）及各動作的列、幀數、fps、循環設定
  frames/<action>/<action>_00.png  每一幀各自輸出為 PNG
  preview/<action>.gif
  report/scores.csv                每次重繪的分數；needs_review 標記需要檢查的幀
  report/summary.md
  reference/character_sheet.png
  reference/character_sheet_front.png   只在有動作使用 --view front 時輸出
```

面對鏡頭拍攝的動作（例如跳舞）可以用以下選項：

- `--view front`：角色改為正面朝向觀眾。會多一次 Muse Image 呼叫，把側面設定圖畫成同一角色的正面設定圖。
- `--mode span`：在整段影片（或 `--start`／`--end` 指定的秒數範圍）平均取幀，不只挑一段爆發動作或一個循環。
- `--frames N`：畫 N 幀（2–48，預設：待機 8、其他動作 10）。每幀含重繪約 US$0.03–0.10。
- `--fps`：播放速度（1–30），或用 `auto` 依影片原速播放。預設：待機 8、其他動作 15、span 為 `auto`。
- `--head-turn`：另外用 SAM 3.1 追蹤主角的臉（約 US$0.04），讓角色的頭跟著轉（正面、微轉、四分之三側、側面、背面）。姿勢導引會多一塊只有形狀、沒有五官的臉部色塊，重繪和評審都會收到一句頭部方向說明。使用 `--view front` 時預設開啟。
- `--sample-fps`：SAM 3.1 每秒追蹤幾張影格（1–60，預設 30，不會超過影片本身）。動作快又複雜、以 60 fps 拍攝時可以調高。

每批 API 呼叫前都會顯示預估費用，且每次呼叫都記錄於 `logs/cost.csv`（三個範例每個動作約
US$0.7；相同要求會直接使用 `cache/`，不再收費）。設定 `ACTSPRITE_OFFLINE=1` 後只會從快取回應：
不需要金鑰，也不會將任何內容傳送至 API。

## 評估

用作者自己的影片做的小規模開發檢查（11/1），每個數字都來自實際執行紀錄；細節、限制與重現指令見
[eval/README.md](eval/README.md)。
E1 採用較早取樣版本保存的 68 個關鍵幀；驗證重畫結果取最多三次嘗試中的最佳結果。
這些歷史數據與 Demo 中 13/16 的跑步案例分開呈現。

| 模型 | 實測結果 |
| --- | --- |
| Muse Image＋驗證迴圈 | 68 個關鍵幀中 79% 通過全部檢查；每幀只畫一次、不錨定第 0 幀時為 32%（E1） |
| Muse Spark 1.3 評審 | 19 張故意改壞的幀抓到 14 張（換色 5/5、少配件 5/5、多配件 4/4、比例錯誤 0/5），19 張正常幀誤判 1 張（E6） |
| SAM 3.1 | 10 段影片中 9 段有 90% 以上的幀追蹤到主角（E4） |
| 費用 | 8–12 幀的動作第一次生成約 US$0.5–1.0（E3） |

![E1：各種繪製方式中通過全部檢查的幀比例](eval/results/e1_chart.png)

E2（與手動在 Unity 製作比較時間）及 E5（遮罩與手繪輪廓比較）尚未執行。

## Unity

匯入工具是一個 Unity 6 套件，放在 [`unity/ActSpriteImporter`](unity/ActSpriteImporter/README.md)。

1. Window > Package Manager > + > *Install package from git URL…*，輸入
   `https://github.com/lilwad-0730/actsprite.git?path=unity/ActSpriteImporter`
   （或選 *Install package from disk…*，指向本機 clone 裡的 `unity/ActSpriteImporter/package.json`）。
2. 選 **ActSprite > Import ZIP…**，挑上面任一個 ZIP。工具會切格（軸心在腳底）、依各動作的 fps 建立動畫，
   建立 Animator Controller（參數 `Speed`、`IsGrounded`，其他動作各一個 Trigger），以及含 Rigidbody2D
   和依角色像素貼合碰撞體的 Prefab。
3. 選 **ActSprite > Build Demo Scene**，按 Play。場景會先放出套件內附的像素騎士（待機、跑步、跳躍、攻擊），
   確保一定有會跑的角色；你匯入的角色排在它後面。A/D 移動、空白鍵跳躍、1–9 播放攻擊或舞蹈等其他動作、
   Tab 切換角色。

已用腳本在全新的 Unity 6000.5.5f1 空專案驗證（先用舊版 Input Manager，再改成只用 Input System）：
三個範例角色匯入時沒有任何警告；每段動畫的關鍵幀都依 fps 等距排列；內附騎士在 `Speed` > 0.1 時從待機切到跑步，
並依序播放 `run_00`–`run_07`；每個角色落到地面和兩個平台上，最低的腳底像素都剛好貼齊表面（誤差 0 像素）。
作者也已在 Play Mode 手動驗收（2026-10-31）。

## 網頁應用程式

線上版：https://huggingface.co/spaces/Andy0730huggin/actsprite 。上傳手機影片，選角色（內建或上傳自己的設計）和動作，
再依序走三個檢查步驟：**1. 追蹤**（只用 SAM 3.1，約 US$0.02，先看關鍵幀的姿勢線稿）、**2. 第一幀**（畫出並檢查第 0 幀）、
**3. 全部幀**（動畫預覽、每一幀的結果，以及給 Unity 匯入工具的 ZIP）。使用的設定會顯示在頁面上，也寫進 ZIP 的
`report/parameters.json`。用 **Start at** 和選填的 **End at** 選擇影片區間，最長 5 秒。
**End at 預設留白**；不填時，從 Start at 起最多取 5 秒，影片剩餘不足 5 秒則取到結尾。
跳躍／攻擊有填結束時間時會使用整段，留白則自動挑動作最劇烈的部分；待機／走路／跑步則在所選區間內找循環。
走路／跑步至少需要兩個完整步態循環；片段太短或取樣稍有差異時，仍可能找不到循環。

| 動作 | 最多格數 | 播放速度 |
| --- | --- | --- |
| idle | 8 | 8 fps |
| walk / run | 16 | 依原影片時間計算 |
| jump | 12 | 依原影片時間計算 |
| attack | 10 | 15 fps |

追蹤最多取樣 30 fps。**Name** 同時設定 ZIP 檔名與內部角色名稱；完成後按 **Rename the ZIP (free)**
可免費重新打包，不會呼叫 Meta API。名稱最多 32 字，保留英數字、`-`、`_`，空白換成底線，其他字元移除。

**Output style 預設為 `pixel`，My own design 也一樣。** 生成前請先閱讀[像素化與原作保真限制](#像素化與原作保真限制)。
兩個繪圖步驟之前都會顯示該次追蹤實際使用的風格；若不希望輸出像素化，請在 Track 前選擇非像素風格。

每位訪客每天最多 5 次追蹤、2 次生成；Space 目前的花費紀錄達 US$40 時停止呼叫。
花費紀錄與每日次數可能隨 Space 重啟歸零，因此這不是持久的帳務上限。其他設定在網頁上鎖定，指令列版可調整。

11/1 本機三步驟實測：跳躍 7/12 格通過（US$0.80）、跑步 9/16（US$1.58）、攻擊 4/10（US$0.947636）。
這些是開發測試，不能保證其他素材的通過率；跳躍與跑步測試早於最新的讀片修正。攻擊是在修正方向後用直立畫面測試，
仍會把窄站姿畫成大跨步，使用前請檢查預覽與橘色未通過幀。先前 8 格版的 US$0.57、三步各 21／76／141 秒，
屬於舊設定的量測，不能代表目前各動作設定的時間。

```powershell
.venv\Scripts\python -m pip install gradio==6.31.0 spaces huggingface_hub
.venv\Scripts\python app.py                    # 本機：http://localhost:7860
.venv\Scripts\hf auth login                    # 只需一次，Token 保留在你的電腦
.venv\Scripts\python scripts/deploy_space.py   # 上傳 app.py、actsprite/、showcase/、characters/ 至 Space
```

## 讓產出更好的實用技巧

### 拍出清楚的全身輪廓

- **衣服以合身、能辨認肢體形狀為主。** 避免過度寬鬆的褲子、長外套與大袖口，讓手臂、腿和軀幹不要連成一大片；
  配件與長髮也盡量不要遮住正在動作的肢體。
- **衣服和背景要有色差，也要有明暗差。** 例如避免深色褲子配深色牆面，鞋子也要與地板有區別。
  使用均勻照明與單純背景，避開其他人物、移動物體與雜物。
- **整個動作都要保留全身。** 頭頂、腳底與移動方向都留空間，跳躍最高點與落地時也不能出框。
  固定相機，減少跟拍、縮放與晃動。
- **拍攝視角要符合想要的角色方向。** 預設側面角色宜用側拍，維持相同朝向；拍攝清晰、光線充足且速度符合需求的一鏡到底片段，
  避免中途剪接或變速。

### 演出可辨識、完整的動作

- 手勢盡量離開軀幹，避免一條肢體完全遮住另一條。側拍時完全重疊的手腳很難從剪影分辨，
  應讓所需的站姿與動作在鏡頭中清楚可讀。
- **走路／跑步至少包含兩個完整步態循環**，並讓選取區間內的速度穩定，避免走到一半轉身或突然停下。
- **跳躍／攻擊包含起始站姿、完整動作、落地或收回。** 用 Start at／End at 框住完整動作，網頁版最多 5 秒；
  刻意停頓也會影響最後的播放節奏。
- **生成前先看灰色姿勢線稿。** 若腳消失、手腳黏在一起或選到錯誤時刻，先調整時間範圍、背景或拍攝位置，再重新追蹤。

### 準備適合小尺寸顯示的角色圖片

- 上傳一個清楚、全身、白底的角色，預設側面視角以朝右為主；使用 PNG 或 JPG，**寬、高都至少 256 px**。
  透明 PNG 會先放到白底；原圖朝左時勾選 **My design faces left**，身體類型也要配合演員。
- 使用明確輪廓、可分辨的四肢與大色塊。細碎花紋、文字和小配件較難保留；
  大披風或遮住手腳的道具，也可能讓姿勢不易辨識。
- 選 `pixel` 時，請以 **64 × 64 工作格線**思考設計：大形狀比細小五官與衣服紋路更重要。
  若不想額外像素化，在 **Track 之前**選 `handdrawn`、`lineart` 或 `ink`；AI 重繪仍可能改變原設計與畫風。
- 先檢查第 0 幀的比例、朝向與重要配件，再生成其餘格子。完成後檢查動畫、橘色標記格、腳底接觸與動作銜接。

以上是輸入素材的準備建議，尚未量測成「提升多少通過率」；即使素材清楚，窄出拳站姿與肢體重疊仍是已知限制。

一般拍攝原則亦可參考 [Move.ai 的服裝與背景對比建議](https://docs.move.ai/knowledge/genesis-performance-considerations)
及 [Rokoko 的拍攝環境指引](https://support.rokoko.com/hc/en-us/articles/28312013117841-How-to-Get-Started-With-Rokoko-Vision)。
它們是一般動作擷取建議，特定片段仍需以 ActSprite 的姿勢線稿與實際輸出判斷。

## 黑客松期間完成（2026 年 10 月 26 日至 11 月 4 日）

這個儲存庫中的所有內容都在黑客松期間建立，詳情請見 Git 紀錄。
線稿角色設計（`man in line.jpg`）由作者的女朋友於 2026 年 10 月 29 日為本專案繪製。
Unity Demo 場景的地牢牆面與地板（`unity/ActSpriteImporter/DemoArt/`）由作者於 2026 年 10 月 30 日以 AI 圖像生成工具製作，
提示詞見 `DemoArt/GenerationPrompts.md`。
唯一的外部輸入是「致謝與授權」中列出的測試影片。

## 致謝與授權

| 套件 | 授權 | 用途 |
| --- | --- | --- |
| [openai](https://github.com/openai/openai-python) | Apache-2.0 | 連接相容 OpenAI 格式的 Meta Model API |
| [meta-sam-parser](https://pypi.org/project/meta-sam-parser/) | SAM License（Meta） | 官方 SAM 3.1 分割輸出解析器 |
| [opencv-python-headless](https://github.com/opencv/opencv-python) | Apache-2.0 | 影格擷取、邊緣偵測與遮罩運算 |
| [NumPy](https://numpy.org) | BSD-3-Clause | 陣列運算 |
| [Pillow](https://python-pillow.org) | MIT-CMU | 圖片讀寫、調色盤與打包 |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | BSD-3-Clause | 載入 `.env` |
| [pytest](https://pytest.org) | MIT | 測試 |
| [Gradio](https://github.com/gradio-app/gradio) | Apache-2.0 | 網頁應用程式（`app.py`）；由 Space 依 `sdk_version` 安裝 |
| [spaces](https://pypi.org/project/spaces/) | Apache-2.0 | Hugging Face ZeroGPU 託管掛鉤（應用程式以 CPU 執行） |
| [huggingface_hub](https://github.com/huggingface/huggingface_hub) | Apache-2.0 | `scripts/deploy_space.py` 將應用程式上傳至 Space |
| [2D Sprite](https://docs.unity3d.com/Packages/com.unity.2d.sprite@1.0/manual/index.html)（Unity） | Unity Companion License | Unity 匯入工具：透過 Sprite Editor Data Provider API 切格 |
| [Input System](https://docs.unity3d.com/Packages/com.unity.inputsystem@1.19/manual/index.html)（Unity，選用） | Unity Companion License | 專案使用 Input System 時的鍵盤操作 |

| 影片 | 來源 | 授權 | 用途 |
| --- | --- | --- | --- |
| `samples/pet.mp4`（未收入儲存庫） | Luis Adolfo Burgos 於 Pexels 發布的 [Close-Up Shot of Dog Walking on the Street](https://www.pexels.com/video/close-up-shot-of-dog-walking-on-the-street-4300700/) | [Pexels License](https://www.pexels.com/license/)（可免費使用與修改） | 四足行走循環的測試輸入。儲存庫只收錄衍生剪影與重繪 Sprite；如需重現，請從連結下載影片。 |
| `samples/dance 2 test .mp4`（未收入儲存庫） | 作者的朋友拍攝 | 已取得舞者同意 | 像素騎士舞蹈範例的輸入。儲存庫只收錄重繪後的騎士 Sprite。 |

## 授權

MIT
