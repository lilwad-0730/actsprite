# ActSprite — 演出動作，直接遊玩

[![English](https://img.shields.io/badge/Language-English-lightgrey)](README.md)

> 黑客松：Meta Global AI Developer Hackathon · 賽道：Indie Developer · 主題：**Build for Your World**

用手機演出一個動作，取得角色一致、可直接在 Unity 使用的遊戲動畫。

**狀態：** 開發中。目前命令列已能執行完整處理流程；Unity 匯入工具與完整網頁流程將接續完成。

## 評審：兩分鐘內完成驗證（不需要 API Key）

**1. 查看完成的輸出。** 每個 ZIP 都是處理流程實際交付給 Unity 的內容：

| 像素騎士：舞蹈（正面、48 幀） | 像素獵犬：行走 | 線稿人物：攻擊 |
| --- | --- | --- |
| ![騎士](examples/previews/knight_dance.gif) | ![獵犬](examples/previews/hound_walk.gif) | ![線稿人物](examples/previews/lineman_attack.gif) |
| [下載 ZIP](https://github.com/lilwad-0730/actsprite/raw/main/examples/actsprite_knight.zip) | [下載 ZIP](https://github.com/lilwad-0730/actsprite/raw/main/examples/actsprite_hound.zip) | [下載 ZIP](https://github.com/lilwad-0730/actsprite/raw/main/examples/actsprite_lineman.zip) |
| 48 幀中有 40 幀通過全部檢查 | 8 幀中有 5 幀 | 8 幀中有 5 幀 |
| Meta API 呼叫費用 US$3.07 | US$0.73 | US$0.67 |

每個 ZIP 內含 Sprite Sheet、供 Unity 匯入工具使用的 `<name>_meta.json`、每一幀的 PNG、GIF
預覽，以及記錄每次重繪分數的 `report/scores.csv`（`needs_review` 代表該幀未通過所有檢查）。
費用是 `logs/cost.csv` 中每個 ZIP 背後所有付費呼叫的總和，包含 SAM 3.1 影片追蹤、角色設定圖，
以及每次重繪與檢查。8 幀的動作約需 3–4.5 分鐘（量測結果見 `spikes/REPORT.md` 的 Day 4），48 幀的舞蹈約 15 分鐘。
獵犬和線稿人物的 ZIP 是從 API 快取重新建立，因此其 `report/summary.md` 會顯示 US$0，並註明原因。

**2. 執行測試。** 不需要金鑰或網路；`tests/test_examples.py` 會依輸出合約檢查三個 ZIP。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest
```

## 運作方式

| 步驟 | Meta 模型 | 工作 |
| --- | --- | --- |
| 擷取 | SAM 3.1（`sam-3.1`） | 追蹤影片中的表演者，取得每幀的像素遮罩 |
| 重繪 | Muse Image（`muse-image-1.0`） | 依角色重繪每個姿勢，以已核准的第一幀作為錨點，一次繪製第 1–7 幀 |
| 驗證 | Muse Spark 1.3（`muse-spark-1.3`）＋SAM 3.1 | 美術總監評分角色一致性；SAM 再次檢查姿勢剪影 |

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

每次執行都會使用 SAM 3.1 追蹤主角、挑選 8 個關鍵幀（跳躍／攻擊取一個爆發動作，待機取一個循環，
行走／跑步取兩步步態）、繪製姿勢導引、以 Muse Image 將每幀重繪成指定角色，並進行檢查
（SAM 3.1 剪影、Muse Spark 1.3 評審、調色盤與腿部動作）。未通過的幀最多重繪兩次。
第 1–7 幀會同時繪製，並以已核准的第 0 幀作為錨點。結果會新增為
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
- `--frames N`：畫 N 幀（2–48，預設 8）。每幀含重繪約 US$0.03–0.10。
- `--fps`：播放速度（1–30），或用 `auto` 依影片原速播放。預設：待機 8、其他動作 12、span 為 `auto`。
- `--head-turn`：另外用 SAM 3.1 追蹤主角的臉（約 US$0.04），讓角色的頭跟著轉（正面、微轉、四分之三側、側面、背面）。姿勢導引會多一塊只有形狀、沒有五官的臉部色塊，重繪和評審都會收到一句頭部方向說明。使用 `--view front` 時預設開啟。
- `--sample-fps`：SAM 3.1 每秒追蹤幾張影格（1–60，預設 30，不會超過影片本身）。動作快又複雜、以 60 fps 拍攝時可以調高。

每批 API 呼叫前都會顯示預估費用，且每次呼叫都記錄於 `logs/cost.csv`（三個範例每個動作約
US$0.7；相同要求會直接使用 `cache/`，不再收費）。設定 `ACTSPRITE_OFFLINE=1` 後只會從快取回應：
不需要金鑰，也不會將任何內容傳送至 API。

## 網頁應用程式

線上預覽：https://huggingface.co/spaces/Andy0730huggin/actsprite
（作品展示＋SAM 3.1 追蹤確認）。

```powershell
.venv\Scripts\python -m pip install gradio==6.31.0 spaces huggingface_hub
.venv\Scripts\python app.py                    # 本機：http://localhost:7860
.venv\Scripts\hf auth login                    # 只需一次，Token 保留在你的電腦
.venv\Scripts\python scripts/deploy_space.py   # 上傳 app.py、actsprite/、showcase/ 至 Space
```

## 黑客松期間完成（2026 年 10 月 26 日至 11 月 4 日）

這個儲存庫中的所有內容都在黑客松期間建立，詳情請見 Git 紀錄。
線稿角色設計（`man in line.jpg`）由作者的女朋友於 2026 年 10 月 29 日為本專案繪製。
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

| 影片 | 來源 | 授權 | 用途 |
| --- | --- | --- | --- |
| `samples/pet.mp4`（未收入儲存庫） | Luis Adolfo Burgos 於 Pexels 發布的 [Close-Up Shot of Dog Walking on the Street](https://www.pexels.com/video/close-up-shot-of-dog-walking-on-the-street-4300700/) | [Pexels License](https://www.pexels.com/license/)（可免費使用與修改） | 四足行走循環的測試輸入。儲存庫只收錄衍生剪影與重繪 Sprite；如需重現，請從連結下載影片。 |
| `samples/dance 2 test .mp4`（未收入儲存庫） | 作者的朋友拍攝 | 已取得舞者同意 | 像素騎士舞蹈範例的輸入。儲存庫只收錄重繪後的騎士 Sprite。 |

## 授權

MIT
