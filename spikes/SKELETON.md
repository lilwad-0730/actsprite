# 骨架引導 spike（2026-11-01）

實驗程式、針對性測試與說明只放 `spikes/`；產出在 `out/_eval/skeleton/`。
不改主流程、requirements、原案例檔案，不 commit。API 沿用 `MetaClient()` 的
`.env`、`cache/`、`logs/cost.csv`。安裝變更只在既有 `.venv`。

## 安裝問題與修復

原命令在 Windows 提供的暫存路徑解包 wheel metadata 時回報
`OSError: [Errno 13] Permission denied`。將安裝程序的 TEMP/TMP 改到工作區後成功，
沒有提升權限，也沒有修改系統暫存設定。這證實換暫存位置可解決本次失敗；
未進一步查證原路徑的 ACL、檔案掃描或暫時鎖定究竟是哪個因素。

在專案根目錄執行的修復命令：

```powershell
New-Item -ItemType Directory -Force spikes\_pip_tmp | Out-Null
$env:TEMP = (Resolve-Path spikes\_pip_tmp).Path
$env:TMP = $env:TEMP
$env:PIP_NO_CACHE_DIR = '1'
$env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
$env:PYTHONUTF8 = '1'
.venv\Scripts\python -m pip install mediapipe==0.10.21
.venv\Scripts\python -m pip install opencv-python-headless==4.11.0.86 pandas==2.3.3 numpy==1.26.4
.venv\Scripts\python -m pip check
```

MediaPipe 0.10.21 要求 NumPy <2，安裝時把 NumPy 2.4.6 改為 1.26.4。
原環境的 opencv-python-headless 5.0.0.93、pandas 3.1.0 要求 NumPy 2，故一併在
`.venv` 改為 4.11.0.86、2.3.3。MediaPipe 另外帶入同版 OpenCV contrib 4.11.0.86。
`pip check` 已通過；MediaPipe、Gradio、pandas、OpenCV 匯入已通過。
原專案 pytest：103 passed in 10.52s。
第一次把整個測試程序設為 ACTSPRITE_OFFLINE=1，造成兩個測試的預期情境不成立；
移除這個環境覆寫後全部通過，未修改測試或主流程。

## 參考與授權

- [MediaPipe 官方 repo](https://github.com/google-ai-edge/mediapipe)：Apache-2.0。
  查閱時 repo 最近 push 為 2026-10-31。依照官方
  [Pose API 說明](https://github.com/google-ai-edge/mediapipe/blob/master/docs/solutions/pose.md)
  使用 RGB、normalized landmarks、VIDEO 模式；未複製程式碼。
  每段影片各自建立 `Pose(static_image_mode=False, smooth_landmarks=True)`，
  連續處理所有格，不跨案例沿用追蹤狀態。
  另核對安裝版本對應的
  [0.10.21 Pose 原始碼](https://github.com/google-ai-edge/mediapipe/blob/v0.10.21/mediapipe/python/solutions/pose.py)。
  [遮擋關節準確度 issue](https://github.com/google-ai-edge/mediapipe/issues/4868)
  顯示遮擋是已知難題；不可把推測的遠側關節當成實測真值。
- 比較 [MMPose](https://github.com/open-mmlab/mmpose)：Apache-2.0，查閱時
  最近 push 為 2025-08-04，維護新鮮度較低。
  [安裝文件](https://github.com/open-mmlab/mmpose/blob/main/docs/en/installation.md)
  需要 PyTorch、MMCV、MMEngine，另有版本配套限制。
  本次採用使用者指定的 MediaPipe，不引入另一組模型或訓練框架。

## 執行與量測方式

```powershell
.venv\Scripts\python -B -m spikes.spike_skeleton --self-check
.venv\Scripts\python -B -m spikes.spike_skeleton --prepare-only
.venv\Scripts\python -B -m spikes.spike_skeleton
```

先從 `track.npz` 取 masks，依順序完整解碼同工作資料夾的 `sam_input.mp4`，
每格 BGR 轉 RGB 後直接送 MediaPipe；不對灰色線稿跑偵測，也不只送關鍵格。
核對每格影像尺寸與最終格數都與 masks 相同，然後留下 `result.json` 的 keyframes。
gait 的大小修正重用 `size_drift`；`make_guides` 重建全部線稿並要求與原 PNG
逐像素一致，否則付費前停止。

VIDEO 模式讀整張原始 RGB，因此關節一開始就在 SAM 遮罩的原圖座標。套用
`fit_to_canvas` 的取整尺寸、遮罩重心與腳底位置，映射到線稿座標。
藍＝演員左手腳、橘＝右手腳、綠＝軀幹與頭；線寬約剪影高度 3%。
每個關節的原圖/線稿座標、visibility、z 保存在 `landmarks/*.json`，
另有 `drawn` 與篩選原因；沒有手動修正或以假資料填補偵測失敗。

可靠性規則固定如下，未依生成結果調整：

- 33 個關節與 17 個主要身體關節，各至少 60% 必須真正落在當格 SAM 遮罩內。
- 個別點 visibility <0.5、超出畫面，或距離遮罩大於身高 2%（至少 1px）不畫。
- 至少 8 個主要身體關節與 3 個肩/髖關節可靠，否則整格回退原剪影。
- 只連接兩端都可靠的線段，不跨過被剔除的關節補線。缺少偵測也回退剪影。
- 整格回退時，不把骨架顏色說明放入生成提示。

`skeleton_quality.csv` 記錄全部關鍵格的 `skeleton_used` 與回退原因，
新舊評分 CSV 也有 `skeleton_used`。真人原圖加骨架保存在各案例的
`source_skeleton/`，只在本機 `out/_eval/`；不送給 Muse Image 或評審。
比較圖也包含真人臉，整個 `out/` 已由既有 `.gitignore` 排除，沒有任何 commit。

僅重畫騎士 3/4、lineman 4/5/6，每格一次。重用 `redraw_parts` 的 fix 欄位
放骨架顏色說明，`Reference` 依 `redraw_action` 的第 0 格錨點建立方式：
騎士保留第 0 格雙腿並檢查 leg drift；lineman 隱藏錨點腿並檢查 leg motion。
採用既有 sheet，不再生成角色參考圖。

新舊圖片以**同一張原灰色線稿**、同一組 512px 評分圖片、同一組門檻重新評分。
IoU 以 `cutout` + `largest_component` + `silhouette_iou` 計算，完全不再呼叫 SAM。
passed 沿用 `FrameScores`，包含調色盤與腿部檢查，不只看 CSV 顯示的三個分數。
原流程以 SAM 得到的分數另存 `original_pipeline_*`，不能與本機去背 IoU 混稱同一次量測。
`redraw/3.png`、`4.png` 與原 chosen attempt 完全相同；手動編輯註記是替換 cells，
本次比較的是使用者指定的 redraw 圖。

新版先以離線模式核對原圖評分的精確快取，再估算需要付費的請求。
5 張重畫與 5 次新評分預估 $0.160，保守預留 $0.47408；
舊圖的 5 次評分重用快取。每次請求前依 cost.csv 的 `spike skeleton ` 前綴
檢查 v1 與 v2 的累計費用，包含先前失敗請求，總上限仍為 $1.00。
新版呼叫前綴是 `spike skeleton v2 video`。
評分圖片上限 512px，文字很短，預留 40,000 input tokens/次；output cap 8192，
包含推理 token。第一次 cap 800 的回覆因 798 reasoning tokens 而被截斷，沒有 JSON；
該次 $0.005456 有記帳，沒有捏造分數。之後提高上限，主流程未改。

每個案例：`guides/`、`old_guides/`、`source_skeleton/`、`landmarks/`、`old_redraw/`、`redraw/`、
`skeleton_quality.csv`、`scores.csv`、`compare.png`。
每列比較：原始畫面加骨架、舊線稿、骨架線稿、舊選定重畫、新重畫；保留影像長寬比。
總記錄見 `run_summary.json`；實際費用以 `logs/cost.csv` 前綴加總為準。

一格一次生成，無法由這次小樣本證明普遍改善；比較圖仍待使用者驗收。

## 初版 v1 已驗證結果（歷史紀錄）

這是逐關鍵格 RGB 偵測的舊結果，已保存在 `out/_eval/skeleton/_history/v1/`。
下表不是目前 VIDEO 版本的新結果。

下表均為本次新舊成對重新評分，數字為舊 → 新。

| 案例 | 格 | IoU | pose | identity | passed |
| --- | --- | --- | --- | --- | --- |
| knight_punch3 | 3 | 0.652 → 0.455 | 9 → 1 | 10 → 10 | False → False |
| knight_punch3 | 4 | 0.659 → 0.416 | 10 → 6 | 10 → 10 | False → False |
| lineman_run20 | 4 | 0.470 → 0.447 | 8 → 4 | 10 → 9 | False → False |
| lineman_run20 | 5 | 0.366 → 0.357 | 3 → 3 | 10 → 10 | False → False |
| lineman_run20 | 6 | 0.811 → 0.398 | 8 → 2 | 4 → 9 | False → False |

5 格新圖的 IoU 全部下降，未觀察到整體改善。評審指出騎士第 3 格仍複製錨點的跑姿，
lineman 新圖仍有過度前傾、腿部或手臂角度錯誤。這些是本次輸出與評審的結果，
不能據此證明所有骨架引導都無效。

`logs/cost.csv` 的 `spike skeleton v1` 前綴：5 次生成、11 次評分，
總計 **US$0.174191**。包含沒有拿到 JSON 的第一次評分 **US$0.005456**；
後續完整執行 **US$0.168735**。沒有 SAM 呼叫。
總 CSV 為 `out/_eval/skeleton/scores.csv`，另有兩案例各自的 `scores.csv`。
已核對 35 張重建線稿完全相同、35 份關節紀錄、指定 5 張新圖、CSV 的格索引，
以及兩張比較圖的尺寸與各列順序。

## VIDEO 版 v2 已驗證結果

已完整連續處理騎士 217 格（480×852）、lineman 100 格（852×480）。
騎士 217 格偵測到姿勢，lineman 87/100 格偵測到姿勢；取出的全部 35 個關鍵格
均偵測成功並通過整格篩選，所以本資料的整格回退數為 0，並非把缺失偵測補成成功。
個別低可見度與離遮罩過遠的點已剔除。指定 5 格的 33 點 inside share 為
90.9%、93.9%、90.9%、90.9%、100%；對應主要 17 點的 inside share 為
94.1%、100%、94.1%、100%、100%。

以下舊圖評分重用精確快取；新圖是 VIDEO 版這輪實際生成、評分的結果。
IoU 均為本機去背法，評審均看同一張原灰色線稿；數字為舊 → 新。

| 案例 | 格 | skeleton_used | IoU | pose | identity | passed |
| --- | --- | --- | --- | --- | --- | --- |
| knight_punch3 | 3 | True | 0.652 → 0.517 | 9 → 6 | 10 → 10 | False → False |
| knight_punch3 | 4 | True | 0.659 → 0.387 | 10 → 2 | 10 → 10 | False → False |
| lineman_run20 | 4 | True | 0.470 → 0.348 | 8 → 3 | 10 → 10 | False → False |
| lineman_run20 | 5 | True | 0.366 → 0.341 | 3 → 4 | 10 → 10 | False → False |
| lineman_run20 | 6 | True | 0.811 → 0.465 | 8 → 3 | 4 → 10 | False → False |

這輪 5 次新生成與 5 次新評分，另 5 次舊評分由快取服務，沒有 SAM 呼叫。
`logs/cost.csv` 的 `spike skeleton v2 video` 合計 **US$0.107490**；
整個 `spike skeleton ` 實驗（含 v1 與首次截斷評分）累計 **US$0.281681**，低於 $1。

107 項測試通過（原有 103 項加 4 項 spike 測試）：
VIDEO 逐格 RGB 順序、格數不符拒絕、低可見度/遮罩外點剔除、
無姿勢與錯誤人物整格回退、剔除關節不補線等行為已檢查。
真人疊圖與五欄比較圖只保存在本機 `out/_eval/skeleton/`，
確認 Git 已忽略且未追蹤這些路徑，未 commit。
骨架是否符合演員，以及新重畫的畫面品質，仍待使用者驗收。
