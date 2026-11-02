# ActSprite Demo 定稿與錄製紀錄

版本：2026-11-02，V6。狀態：已驗證，使用者已確認節奏與視覺效果可接受，並已發布至
[YouTube](https://youtu.be/4VDyiQ0EOP4)。已核對 YouTube 影片標題；本次未重新觀看線上全片。

定稿片長 **161.6 秒（2:41.6）**、1920×1080、30 fps，共 4848 格。片頭標題 6 秒，首句字幕約 6.9 秒出現；
最後一句字幕在 151.4 秒結束，之後保留約 10 秒配樂收尾。片頭、片尾配樂比旁白段的基準提高 6 dB，平順進出。

主線使用這次網頁與 Unity 錄影的同一份 knight/run 成品：16 格、20 fps、0.8 秒循環，**13/16 格通過自動檢查**。
先前 Unity 驗收的 12/16 成品是另一份輸出；正式影片的畫面、字幕及補錄配音均以 13/16 為準。
人工驗收不會改寫生成分數。角色上傳補錄展示 goblin 設計選項，實際生成流程使用 Pixel knight。

## 參考影片

以下影片由 [Google 官方得獎公告](https://developers.googleblog.com/en/announcing-the-winners-of-the-gemini-api-developer-competition/)收錄，屬於 2024 Gemini API Developer Competition。2026-11-02 已核對影片網址及 YouTube 公開標題；未逐秒分析剪輯。

- [Introducing ViddyScribe](https://www.youtube.com/watch?v=MsN_YbwviUU)：Best Web App。建議參考如何讓「影片輸入→AI 處理→可檢視的輸出」成為展示主線。
- [outdraw.AI](https://www.youtube.com/watch?v=e16IQA1GGw4)：Most Creative App。建議參考以遊戲實際運作展示 AI 的角色。
- [JAYU](https://www.youtube.com/watch?v=shnW3VerkiM)：Best Overall App。建議留意產品實際操作與 AI 能力說明如何銜接。

## 定稿時間軸

以下為 V6 約略段落邊界；實際逐句時間以 `../Demo/ActSprite_Demo_v6_en.srt` 為準。

| 段落 | 剪輯目標時間 | 畫面 | 螢幕文字（不念） |
| --- | --- | --- | --- |
| 1 | 00:00–00:17 | 片頭標題與配樂，接原始跑步／騎士並排及 Unity 移動畫面。 | Phone video → Playable character |
| 2 | 00:17–00:33 | 角色設定圖與同一次生成的動畫並排。 | Character sheet + frame-0 reference + checked redraws |
| 3 | 00:33–00:55 | 選影片、展示自訂角色上傳，切回 Pixel knight 顯示時間欄位，追蹤並檢視灰色姿勢線稿。 | SAM 3.1 · Actor tracking |
| 4 | 00:55–01:20 | First frame 預覽與評分 → All frames → 完成後的逐格結果。等待時間縮短並標示。 | Muse Image · Redraw / Muse Spark 1.3 · Review / Waiting shortened |
| 5 | 01:20–01:41 | 下載 ZIP、Unity 匯入、Prefab 與 A／D 操作。 | 16 frames · 20 fps · 0.8 s loop |
| 6 | 01:41–02:04 | 完整呈現 E1 圖表，保留方法註記與歷史測試標籤。 | Historical E1 · 68 keyframes · Earlier sampler · Best of up to 3 attempts |
| 7 | 02:04–02:22 | 原角色與本次生成角色並排，說明畫風、細節與像素化限制。 | This run: 13/16 passed · Artistic review still needed |
| 8 | 02:22–02:42 | Unity 操作、片尾網址與最後一句旁白，配樂抬升後淡出。 | andy0730huggin-actsprite.hf.space |

## 完整逐字稿

只朗讀「英文旁白」。中文為理解與字幕翻譯參考，時間、標題與畫面文字不朗讀。

### 1. 00:00–00:17｜先展示成果

**英文旁白**

This is a movement from a phone video. And this is the same movement, turned into a playable character. This is ActSprite.

**中文對照**

這是一段手機拍攝的動作。這是由同一段動作產生、可以實際操作的角色。這就是 ActSprite。

### 2. 00:17–00:33｜說明痛點

**英文旁白**

For a solo developer, character animation takes time. Generating frames with AI adds another challenge: keeping the same design across the sequence. ActSprite starts with a movement you can perform.

**中文對照**

對獨立開發者來說，製作角色動畫需要時間。用 AI 生成逐格圖片，又會遇到另一個挑戰：讓整段動畫維持同一個角色設計。ActSprite 從你親自演出的動作開始。

### 3. 00:33–00:55｜上傳與追蹤

**英文旁白**

Start with a short video and choose a character. You can also upload your own design. Select the part of the clip you want, then track it. SAM 3.1 isolates the actor, and ActSprite selects keyframes and creates silhouette guides. For this demo, we're using the running clip.

**中文對照**

先放入一段短影片，選擇角色，也可以上傳自己的設計。設定要使用的影片區間，開始追蹤。SAM 3.1 分離出演員，ActSprite 再選取關鍵格、建立剪影姿勢線稿。這次使用的是跑步片段。

### 4. 00:55–01:20｜生成與驗證

**英文旁白**

Muse Image redraws these poses using the character sheet and the first frame as references. Muse Spark 1.3 scores pose and identity, while SAM checks the silhouette. Failed frames can be redrawn automatically, and the best result is kept. Waiting sections are shortened in this video.

**中文對照**

Muse Image 參考角色設定圖和第一格，重畫這些姿勢。Muse Spark 1.3 評估姿勢與角色身分，SAM 則檢查剪影。檢查未通過的格子可以自動重畫，系統會保留評分最好的結果。影片中的等待時間已縮短。

### 5. 01:20–01:41｜匯入 Unity 並操作

**英文旁白**

Now download the ZIP and import it into Unity. The importer slices the sprite sheet, builds animation clips and creates a character prefab with a collider. This running animation has sixteen frames, played at twenty frames per second. Press Play, then use A and D to move.

**中文對照**

接著下載 ZIP，匯入 Unity。匯入工具會切割 Sprite Sheet、建立動畫片段，並產生帶有碰撞框的角色 Prefab。這段跑步動畫有十六格，每秒播放二十格。按下 Play，就能用 A 和 D 左右移動。

### 6. 01:41–02:04｜用數據說明機制

**英文旁白**

We also tested the consistency mechanism on sixty-eight saved keyframes. The full-check pass rate rose from thirty-two percent for single drawings without an anchor to seventy-nine percent with anchoring and checked redraws. This was a small development test using an earlier sampling version.

**中文對照**

我們也用六十八張已儲存的關鍵格，測試維持一致性的機制。沒有第一格錨點、只生成一次時，通過全部檢查的比例是百分之三十二；加入錨點及驗證重畫後，提高到百分之七十九。這是採用較早取樣版本的小型開發測試。

### 7. 02:04–02:22｜如實說明限制

**英文旁白**

ActSprite redraws your character, so its style, proportions, and design details may change. Pixel export simplifies it further. Here, thirteen of sixteen frames passed the checks. Artistic review is still needed.

**中文對照**

ActSprite 會重新繪製角色，因此原本的畫風、比例與設計細節可能改變。像素化輸出會進一步簡化畫面。這次案例有十六格中的十三格通過檢查，成品仍需要美術判斷與人工檢視。

### 8. 02:22–02:42｜收尾

**英文旁白**

ActSprite is built for solo developers and game jams. Try the live demo. Bring your movement into Unity. Act it out. Play it in.

**中文對照**

ActSprite 為獨立開發者與 Game Jam 而做。試試線上 Demo，把你演出的動作帶進 Unity。Act it out. Play it in.

## 本機素材與證據

下列路徑以專案根目錄為準；out/ 的真人素材、截圖與產出保留本機。

| 素材 | 路徑／來源 | 用途 |
| --- | --- | --- |
| 已驗證可播放的跑步來源影片 | out/_eval/acceptance/01_upload_run_h264.mp4 | 上傳示範；演員與騎士並排 |
| 本次錄影的 ZIP | ../unity test/actsprite_knight (1).zip | 網頁下載與 Unity 匯入的同一成品 |
| 本次跑步預覽 | out/_eval/demo/edit_v1/recorded_export/actsprite_knight/preview/run.gif | 角色對照與循環展示 |
| Unity 實際操作錄影 | ../Demo/Unity 操作錄影.mp4 | 本次匯入與可操作成果 |
| 16 格、20 fps、13/16 檢查結果 | out/_eval/demo/edit_v1/recorded_export_info.json | 本次成品數據來源 |
| 較早的 Play Mode 自動檢查 | out/_eval/acceptance/downloaded/unity_play_result.txt | 另一份 12/16 成品的落地、D/A 移動與停止證據 |
| 定稿、字幕與驗收紀錄 | ../Demo/ActSprite_Demo_v6.mp4、../Demo/ActSprite_Demo_v6_en.srt、out/_eval/demo/edit_v6_bookends/validation.json | 片長、解碼、音量、字幕順延及使用者驗收 |
| 歷史 E1 圖表及方法 | eval/results/e1_chart.png、eval/README.md | 68 關鍵格、32% 與 79% 的歷史開發比較 |
| 線上版 | https://andy0730huggin-actsprite.hf.space | 網頁操作錄影及片尾入口 |

## 錄製時的執行細節

- 網頁沿用 Track → First frame → All frames 三步。呈現自動檢查及重畫結果。
- 若直接使用已生成的成品來展示，畫面標示「Previously generated result」；有錄到生成等待才採用縮時，並標示實際加速倍率或「Waiting shortened」。
- Unity 若透過 Build Demo Scene 建立場景，預設第一位是套件附的 demo_knight；按 Tab 切到本次匯入的 knight，讓畫面左上角名稱清楚可見。
- E1 的 32%／79% 是較早取樣版本、68 張保存關鍵格的小型測試。圖表 C 為最多三次嘗試後保留最佳分數；本次跑步結果另外顯示 13/16。
- AI 重繪本身可能改變畫風、比例與設計細節；pixel 輸出會進一步簡化。選擇非像素風只能避開程式的像素化步驟，仍不能保證忠實保留原稿。片中保留原角色與生成角色的並排比較，作為需要人工美術檢視的動畫原型展示。
- 真人只使用已取得同意的素材。片尾使用線上版網址；GitHub 連結須在公開並完成匿名存取檢查後加入。
- 已加入網頁設定補錄及 13/16 配音，並匹配音量、微調 EQ。補錄中的 Start=0、End 留白，沒有捏造輸入秒數的操作。
- 配樂為使用者提供的 `insomnia.wav`。剪輯過程未新增付費模型呼叫；真人影片、聲音、剪輯中間產物與完整成片保留本機，不放進 Git。
