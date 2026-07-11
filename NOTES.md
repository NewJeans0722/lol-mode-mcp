# NOTES.md — 開發日誌與重要決定

> 給下一個 session(和未來的自己):開場先讀這份。
> 專案需求原文在 `LOL_MCP_BRIEF.md`。

## 目前狀態(2026-07-09)

**Phase 1~3 完成 + 網頁查詢 UI 上線(2026-07-10)**

- MCP(給 Claude):`https://lol-mode-mcp.onrender.com/mcp`(v0.1.0)
- 網頁(給人):`https://lol-mode-mcp.onrender.com/`
  海克斯圖鑑(圖卡+搜尋+稀有度篩選)、競技場平衡、Patch 改動
  (後兩者 2026-07-10 新增,已部署驗收)、ARAM 平衡表(可排序)。
  同一個 server 三個出口:`/`、`/api/*`、`/mcp`,
  共用資料層與快取(web.py + server.py 的 custom_route)。

使用者已定案的範圍決定:
- **出裝統計不做**(使用者自己去 op.gg 查),爬蟲偵察中止。
- Mayhem 線索:cherry-augments.json(原始檔)有 638 筆,含 `ARAM_` 前綴
  的 Mayhem 強化;wiki 另有 Module:ArenaAugmentData/data(255 筆,
  英文 description/notes)可做補充註記。

## 競技場擴充路線圖(2026-07-10 偵察完畢,資料源全部驗證過)

使用者要求:競技場數值調整、英雄海克斯限定、完整機制(含投票)、
相對上一版的 nerf/buff 要寫出來。偵察結論:

1. ✅ **競技場每英雄數值調整 — 完成(2026-07-10,見日誌)**
   - 基礎數值:`Module:ChampionData/data` 的 `stats.ar` 區塊(45 英雄),
     欄位 hp_base/hp_lvl/dam_lvl/arm_lvl/as_lvl(對基礎值/成長值的加減)。
     已併入 aram.py 的 `_fetch_wiki_data`(同一次抓取,data 多個 "ar" key)。
   - 逐技能調整:`Module:MapChanges/data/ar`(~100KB、587 條,
     -- Champions/-- Items/-- Runes 三段),wikitext 清理器在 `wikitext.py`,
     解析/分組/tool 在 `arena_balance.py`。
   - 成品:tool `arena_balance(champion)` + 網頁「⚔️ 競技場平衡」分頁
     (`/api/arena-balance`)。
2. ✅ **投票機制(2026-07-11 完成,見日誌:mode_mechanics)**
   - wiki 頁 `Arena`(11 萬字)有完整章節:Fame system、Champion select、
     Battlefields、Round structure、Shop/Combat/Vote Phase、
     Mode-Specific Changes、Patch History。
   - Vote Phase:第 2、8 回合前全體傳送到 Reckoner Arena 投票 25 秒,
     三選一「Guest of Honor」英雄 NPC,套用全大廳永久規則;每位 Guest
     只出現在特定投票輪(Riven 例外)、每場最多一次。
   - 實作:充實 mode_mechanics.json(手工整理翻譯)+ 網頁機制分頁;
     Guests 完整名單在 Arena 頁 Vote Phase 章節後半(尚未逐一抽出)。
3. **海克斯英雄限定 — 仍無結構化資料源(再次確認)**
   - Arena 頁與 Arena/Augments 頁都沒有 per-champion eligibility;
     遊戲內規則(如一轉就贏只給有旋轉技能的英雄)未公開。
   - 能做的:強化說明本身已自述條件(「你的旋轉類技能…」);
     在 UI 上標注「此類強化依英雄技能組決定是否出現」。
4. ✅ **相對上一版的改動 — 完成(2026-07-10,見日誌)**
   - 成品:tool `arena_patch_notes(patch, query)` + 網頁「📋 Patch 改動」
     分頁(`/api/patch-notes`),資料源是各 patch 頁的 Arena 段落。
   - 裝備名已確認:使用者說的是 **3430「殞落之祭」= Rite Of Ruin**
     (「伊卡西亞殞落」是口誤);查詢翻譯靠 ddragon item.json 中英對照。
   - Arena/Patch history 子頁(5th launch 等)是「模式改版史」,
     只有大改版(V26.09)有內容,逐版 nerf/buff 還是在 patch 頁。
5. 雜項:`{{ 字串表引用 }}` bug 已修(formatting.py `_STRING_TABLE`,
   新引用的查法:cdragon `game/zh_cn/data/menu/en_us/lol.stringtable.json`
   的 entries,key 小寫;zh_tw 不存在,需手工繁化)。

- ✅ 專案骨架(uv + src layout + console script `lol-mode-mcp`)
- ✅ `get_augment` / `list_augments`(競技場強化,中英雙語搜尋)
- ✅ `aram_balance`(LoL Wiki Lua 模組解析,含英雄名中英正規化)
- ✅ `arena_balance`(競技場基礎數值 + 逐技能調整;2026-07-10)
- ✅ `arena_patch_notes`(逐 patch 競技場改動,query 支援中文;2026-07-10)
- ✅ `mayhem_balance` stub(回「暫未支援」)
- ✅ resource `lol-mode://mode-mechanics`(骨架 JSON,內容待作者校訂,搜 TODO)
- ✅ 28 個單元測試全過;stdio 與 streamable-http 都用真 MCP client 驗證過
- ⬜ 接上 Claude Desktop 實測 —— **這台機器沒裝 Claude Desktop**
  (`%APPDATA%\Claude` 不存在),裝好後照 README 的 json 設定即可。
  替代:專案根目錄有 `.mcp.json`,在本資料夾開 Claude Code 就能直接用。
- ⬜ Phase 3:push GitHub → FastMCP Cloud → README 填真實網址 + 截圖 → v0.1.0 tag

## 驗證方式

```bash
uv run pytest                              # 單元測試
uv run mcp dev src/lol_mode_mcp/server.py  # MCP Inspector(互動)
uv run lol-mode-mcp                        # stdio 啟動
MCP_TRANSPORT=streamable-http uv run lol-mode-mcp   # HTTP 啟動(:8000/mcp)
```

## 架構速覽

```
src/lol_mode_mcp/
  server.py      FastMCP 實例 + 4 tools + 1 resource + transport 切換(main)
  arena.py       競技場強化:抓取/雙語合併/模糊搜尋/排版
  aram.py        ARAM 數值:wiki Lua 模組解析/排版;mayhem stub
                 (同一次抓取也解析競技場 "ar" 基礎數值區塊)
  arena_balance.py 競技場每英雄調整:MapChanges/ar 解析、依英雄分組、tool
  patch_notes.py 逐 patch 競技場改動:patch 頁枚舉/Arena 段落解析/中文查詢翻譯
  wikitext.py    wiki {{模板}}/[[連結]] → 純文字(MapChanges + patch 頁共用)
  champions.py   英雄名正規化(Data Dragon en_US + zh_TW)+ 技能台服名
                 (championFull.json,含變形英雄複合技能名切分)
  formatting.py  @佔位符@ 代入 dataValues、HTML 標籤清理
  cache.py       記憶體 TTL 快取(12h),重抓失敗退回 stale 並標注
  http_util.py   httpx 共用(timeout 15s、User-Agent)
  data/mode_mechanics.json   手工校訂的機制說明(掛成 resource)
```

## 資料源實測發現(和 brief 的差異)

1. **zh_tw 的競技場 JSON 存在**(brief 擔心沒有):
   `https://raw.communitydragon.org/latest/cdragon/arena/zh_tw.json`,
   226 個強化。en_us 與 zh_tw 都抓,以 augment `id` 合併成雙語索引。
   zh_tw 抓不到時自動退回 en_us(patch 剛更新可能發生)。
2. **稀有度不只三種**:`rarity` 實測值 0=白銀(68)、1=黃金(76)、
   2=稜彩(57)、**4=特殊(25)** —— 稜彩道具/鐵砧/獎勵類
   (神羊喘息、冰霜之錘、「獲得能力值鐵砧」等)。brief 只提三種,
   我加了「特殊(special)」分類。⚠️ rarity=3 沒出現過,語意不明。
3. **`desc` vs `tooltip`**:兩者都有 `@變數@` 佔位符,但只有 `desc`
   的佔位符和 `dataValues` 直接對得上(例 APAmp=0.15 → `@APAmp*100@` → 15%);
   `tooltip` 引用遊戲內即時計算值(`@f1@` 等)離線解不出來。
   **顯示一律用 `desc`**。指向 calculations 公式的佔位符會部分求值
   (等級內插「100–300(隨等級)」、屬性/層數加成註記,見 formatting.py
   `_eval_calc`);完全解不出退「(依遊戲內數值)」,不再出現孤立「?」。
   另有 `@spell.Augment_{apiName}:{Key}@` 跨引用格式(實測都指自己的
   dataValues),`_SPELL_REF` 處理。
4. **`dataValues` 索引語意(2026-07-11 已驗證,先前的懸案)**:
   每 key 長度 7 陣列 + `MaxLevel` 欄位(陣列或**純量**,17 個強化缺
   =1)。**index 1..MaxLevel = 第 1..N 星數值**,之後是外插垃圾
   (天界之身 Health=[1000,1000,2000,3000,4000...] ★3 → 1000/2000/3000,
   4000+ 是垃圾;全能之魂龍魂 2/3/4);index 0 通常≈1星值但不可靠
   (蜂群意識 StartingBees[0]=0)。分布:1★=79、2★=100、3★=47。
   例外 4 個(MaxLevel=1 但值遞增=隨遊戲內條件成長,維持整條串接):
   不朽守衛/火狐 BaseDamage、重創劇毒 DebuffDuration、鐵砧賭博
   PrismaticCostReduction。顯示規則在 formatting.py `_render_values`,
   可升級強化文末自動加「(可升級,最高 ★N…)」註記。
5. **patch 版本**從 `content-metadata.json` 取,原始格式帶 build 資訊,
   修剪成 `16.13` 這種人類可讀格式,附在每個回覆末尾。
6. **ARAM 數值源**:採 MediaWiki API 抓 `Module:ChampionData/data` 的
   wikitext(一個 request 拿全部英雄),regex 解析 Lua table 的
   `["aram"] = {...}` 扁平區塊。實測 161/175 英雄有 aram 調整。
   欄位:dmg_dealt / dmg_taken / healing / shielding / ability_haste /
   total_as / tenacity / energyregen_mod。
   解析出 0 筆時視為失敗(觸發退回舊快取),防 wiki 改版悄悄變空資料。
7. **英雄名對照**:Data Dragon `versions.json` → 最新版 en_US + zh_TW
   `champion.json`。wiki 的 key 是英文顯示名(Wukong),ddragon id 是
   MonkeyKing,兩者都能查。模糊比對:全等 > 包含(唯一)> difflib 建議。
8. **ARAM 欄位語意實測**:`tenacity` 是乘數(值域 1.1/1.2),
   `ability_haste` 是加值(±5~20),其餘皆乘數。一開始把 tenacity
   誤判為加值,已修正並加測試。
9. wiki 模組裡也有 `urf` / `nb` / `ofa` / `usb` / `ar` 等模式區塊,
   `parse_champion_mode_data(text, mode_key)` 已參數化,未來擴充容易。
   **沒有** mayhem 專屬區塊 —— mayhem_balance 維持 stub。

## 重要技術決定(含理由)

- **官方 MCP SDK 的 FastMCP**(`mcp[cli]`),不是第三方 `fastmcp` 2.x 套件。
  ⚠️ 若 FastMCP Cloud 部署時要求 `fastmcp` 套件,再評估切換(介面幾乎相同)。
- **同步 tool 函式**:FastMCP 自動丟 thread pool,不卡事件迴圈;
  程式簡單很多,工作量(抓 JSON + 查表)也不需要 async。
- **transport 用 `MCP_TRANSPORT` 環境變數切換**,預設 stdio。
  ⚠️ 踩坑:這版 SDK 的 `FastMCP()` 建構子把預設 host/port 明確傳進
  Settings,`FASTMPC_*` 環境變數會被蓋掉 —— 所以 `main()` 自己讀
  `PORT` / `FASTMCP_PORT` / `FASTMCP_HOST`,HTTP 模式預設綁 0.0.0.0。
- **`stateless_http=True`**:serverless 不保證 session 黏著,必開。
- **快取**(cache.py):記憶體 dict + 時間戳,TTL 12h
  (`LOL_MCP_CACHE_TTL` 可調)。過期重抓失敗 → 退回 stale 並在回覆
  加「⚠️ 資料可能過期」;完全沒資料 → 回「查詢失敗」與原因。
- **logging 全走 stderr**:stdio transport 下 stdout 是協定通道,
  印到 stdout 會弄壞 MCP。等級用 `LOL_MCP_LOG_LEVEL` 調。
- **「無調整」≠「查詢失敗」**:aram_balance 明確三分 —— 有調整(列數值,
  🟢增益/🔴削弱)、無調整(明說基準值)、失敗(明說原因)。
- **模糊搜尋策略**(arena.py `score_augment`):同名 100 > 名字含查詢 90
  > 查詢含名字 80(整句問話場景)> 說明命中 40 / difflib。
  ≥80 直接展示;<80 展示最接近一筆的完整內容 + 其他候選清單。
- **mode_mechanics.json 放在套件內**(`src/lol_mode_mcp/data/`),
  打包安裝後也讀得到;repo 直跑當然也行。

## resource vs tool(brief 要求解釋)

- **tool**:模型看到使用者問題後「主動呼叫」的函式,有參數有邏輯
  (get_augment 等 4 個)。
- **resource**:掛在固定 URI 的唯讀內容,像一份文件;由「使用者/客戶端」
  附加到對話 context,模型不用呼叫就讀得到。
- Claude Desktop 讀法:對話輸入框的「+」附加選單 → 選這個 server →
  點 `mode-mechanics`,JSON 內容就進入對話。

## 待辦與待決事項

1. ✅ ~~mode_mechanics.json TODO 校訂~~(2026-07-11 全檔重寫,無 TODO)。
2. **(要你動手)** 裝 Claude Desktop 後,把 README「本機開發」段的
   json 貼進 `claude_desktop_config.json` 實測。
3. Phase 3 部署時:README 的 `<部署後的公開網址>` 佔位、截圖、
   GitHub repo 網址(http_util.py 的 User-Agent 裡也有佔位)要補。
4. 可考慮:mayhem 資料源(wiki 是否新增 mayhem 模組)、
   list_augments 加英文 locale 的標題在地化(目前少量中文字樣寫死)。

## 日誌

- **2026-07-11**(機制功能 + Mayhem 圖鑑 + 選單重排):
  - **偵察結論(重要,別再查)**:強化的英雄限定名單與出現機率
    **不存在於任何公開來源**——官網 notes、wiki 三頁、cdragon
    (arena json/cherry-augments 無相關欄位)、客戶端
    `gameplay.augmentselection.bin.json`(只是 UI/粒子特效,
    "probability" 是特效參數)都查過;邏輯在 Riot 伺服器端。
    但**裝備有職業池明文**:職業傳說鐵砧只開該職業池(法帽=法師池),
    池子清單在 wiki —— 使用者問「純物理鬥士抽不到法帽」的答案。
  - **mode_mechanics.json 全檔重寫**(原 TODO 骨架淘汰):arena
    (選取規則/回合表/職業鐵砧/23 位貴賓含效果/誠實聲明)、
    aram(基本規則/光環補正)、mayhem(MXP 進度/Golden Reroll/
    專屬內容:終末戰戟、殞落之祭、破曉綻放之劍)。內容為自撰中文
    事實摘要。新 tool `mode_mechanics(mode)`(mechanics.py)+
    `/api/mechanics`(貴賓補台服名與頭像)+ 網站「機制」分頁。
  - **Mayhem 海克斯圖鑑**(mayhem_augments.py):說明文字源 =
    wiki `Module:MayhemAugmentData/data`(106KB、220 條,tab 縮排,
    英文 wikitext 用既有清理器);名稱/圖示 = cherry-augments
    (218/220 對上,_name_key 正規化)。cdragon 沒有含說明的
    Mayhem 檔(kiwi-hub.json 是空的,已查)。`/api/mayhem-augments`;
    圖鑑分頁加「競技場/ARAM Mayhem」模式 chips。
    ⚠️ Mayhem 說明官方無中文,顯示英文並在 UI 註明。
  - **選單重排**:海克斯圖鑑 / 競技場平衡 / ARAM 平衡 / Patch 改動 / 機制。
  - 驗收:111 tests;本機 e2e(tool 三 mode、兩個新 API、node 渲染
    226+220 卡、機制 5 節)全過。
- **2026-07-11**(側邊主角背景 + README 分家):
  - 背景改「右側主角展示」:#bg 改為右側固定欄(min(48vw,920px)),
    用 CSS mask 往左淡出到內容底下,人物(原畫主體通常在圖中央)
    落在右側邊欄不被內容擋;遮罩改輕薄。≤1100px 退回全幅淡化。
  - README 公開版拿掉開發者內容(本機開發/部署/環境變數→濃縮成
    「自行架設」兩行);完整版搬到 **README.dev.md(已 gitignore,
    僅本地)**。⚠️ 已提醒使用者:NOTES.md 本身仍在公開 repo,
    要不要也改私有待使用者決定。
  - GoatCounter 設定步驟寫在 README.dev.md 環境變數表(使用者還沒設)。
- **2026-07-11**(強化說明總整治,使用者抓到的顯示 bug):
  使用者質疑「天界之身 1000/…/6000 生命,但升星只有三階」→ 完全正確。
  三類問題一次修(偵察細節在「資料源實測發現 #3/#4」與
  `~/.claude/plans/shiny-weaving-penguin.md`):
  - **星級切片**:dataValues 的 MaxLevel 欄位一直都在,index 1..N
    = 各星級值,之後是垃圾。`_render_values` 依 MaxLevel 切片;
    Augment 加 max_level;tool 詳情/網頁卡片顯示 ★N(147 個可升級)。
  - **@spell.Augment_X:Y@**(4 處,飛影跑法/守護家園):實測 X 都是
    自己的 apiName,`_SPELL_REF` 解回自身 dataValues(peers 備援)。
  - **「?」→ 部分求值**:`_eval_calc` 處理 NamedDataValue/
    ByCharLevelInterpolation(→「100–300(隨等級)」)/StatBy*(→
    「(+隨最大生命加成)」,mStat 對照表只收查證過的 9=暴擊機率、
    12=最大生命)/SumOfSubParts/BuffCounter/雜湊 range 型別
    {ee18a47b};解不出退「(依遊戲內數值)」。
    ⚠️ 佔位符自帶 *100 乘數要優先於公式的 mDisplayAsPercent。
  - 驗收:108 tests;全量掃描 226 強化 **0 未解佔位符 0 @ 殘留**
    (「404找不到增幅裝置」英文原文的 ?!?!? 是彩蛋標點,不是殘留)。
  - 日後 patch 更新複驗法:跑全量掃描腳本(見計畫檔驗證節)。
- **2026-07-11**(背景原畫切換):右上選單可換柔依/布蕾爾全造型背景
  (官方正名是「柔依」「布蕾爾」,不是柔伊/布雷爾),預設「泳池狂歡
  柔依」。
  - 圖源 = Riot Data Dragon splash CDN(`cdn/img/champion/splash/
    {cid}_{num}.jpg`),`/api/backgrounds` 伺服器端逐 num HEAD 探測
  (⚠️ 炫彩造型回 403 沒有獨立原畫,自動濾掉;柔依 45→10、
    布蕾爾 29→4),官方出新造型清單自動跟上。首次組建 ~24s
  (74 個 HEAD),快取 12h + warmup 涵蓋。
  - 前端 #bg 固定圖層(z-index -3)+ 深/淺主題各自的漸層遮罩保持
    可讀性;選擇存 localStorage;要加英雄改 web.py `BG_CHAMPIONS`。
- **2026-07-11**(去 AI 味改版:Hextech 風 + zhongiii 品牌):
  使用者嫌「太 Claude 味」(裝飾 emoji、通用膠囊風)。已拍板:
  Hextech 視覺 + 署名 zhongiii(GitHub 帳號不改)+ tool 輸出
  「裝飾拿掉、語意保留」。
  - 網站:Cinzel 襯線(標題/nav)、卡片圓角→2px + 金色角框
    (.acard::before/::after L 形)、chips 膠囊→45° 切角(clip-path)、
    背景極淡六角紋(body::before + SVG data URI)、
    **個人強調色粉藍 --accent**(lang active/排序箭頭/連結 hover/
    官方繁中原文標記)、by zhongiii 字標、Z 六角 favicon(data URI)。
    主題鈕 ◐/◑(不用 emoji)。
  - tool 輸出:⚔️🏔️📋🚧 標頭拿掉、📌→「資料來源:」、💡→「提示:」、
    ℹ️→「注意:」;🟢🔴⚠️🔤 保留;稀有度 ⚪🟡🌈📦 視為階級色碼保留
    (使用者若不要再拿)。
  - 效能遺留驗證:prod Cache-Control/gzip 其實正常(先前量到 None
    是冷啟動路徑假象);快取熱時第二請求 0.2s。
  - 視覺細節(角框粗細/紋理濃淡/字體大小)待使用者實際看過再迭代。
- **2026-07-11**(網站效能:使用者反映「其他人用卡卡的」):
  診斷:①/api/arena-balance 每個請求重算全部翻譯,實測 **6.2 秒/次**;
  ②無 gzip(161KB 裸傳)③無 Cache-Control ④Render 免費版冷啟動 30~60s。
  修法(web.py `_cached_json` + `warmup`):
  - **回應層快取**:組好的 payload 進 TTL 快取(1h),之後請求只剩
    序列化+gzip。實測 arena-balance 6.2s → **30ms**。
  - **gzip**(>10KB 且客戶端支援):161KB → 33KB。
  - **Cache-Control: public, max-age=300**:瀏覽器再擋 5 分鐘。
  - **開機暖身執行緒**(server.py main):抓齊資料+預算 6 個 payload,
    實測 10 秒內完成。
  - **防休眠**:`.github/workflows/keepalive.yml` 每 12 分鐘 ping 首頁
    (⚠️ repo 60 天沒 commit 會被 GitHub 自動停用排程,會寄信)。
  - ⚠️ 測試坑:Windows 上用 `localhost` 打 API 會有固定 ~2s 延遲
    (IPv6 fallback),量測要用 `127.0.0.1`。
- **2026-07-11**(arena_balance 全中文化 = 🔤 歸零):
  - **句內名詞代換**:translate.py 的 name_map 現在也做句中代換
    (compile_name_map 單一 alternation regex,長詞優先);
    arena_balance.build_entity_name_map 彙整強化(cdragon)+ 裝備
    (ddragon)+ 英雄名 + 該英雄技能(championFull),
    「Boulder Toss cooldown changed to…」→「巨岩拋擲冷卻時間改為…」。
  - **人工對照檔 data/mapchanges_zh.json(246 句,Claude 逐句翻譯)**:
    規則翻不動的自由句整句對照;譯文中的專有名詞保留英文,
    執行期由 name_map 換成官方台服名(Bone Skewer→刺骨串叉、
    Ghostcrawlers→鬼蟹、Your Cut→你也有份 全自動)。
    key = 去除 **/* 標記後的英文原句;**wiki 改句子會 miss → 退回
    規則/🔤,屆時把新句子補進這個檔即可**(用 NOTES 這段的量測腳本找)。
  - 實測:MapChanges 876 行 **0 句 🔤(100%)**。
  - 術語表再 +30(per/every/darkin/匕首/羽刃…);
    整行特例 general→整體、stats→基礎數值。
- **2026-07-11**(官方繁中 patch notes 上線 = patch 改動全中文化):
  使用者要求把 🔤 全部消掉(中文版不要再有英文句)。
  - **official_notes.py(新)**:解析 Riot 官方繁中 patch notes,
    中文版 patch_notes(三個 scope)直接用官方原文 —— 專有名詞全對
    (咒法/升級收藏家/風險計算這些 cdragon 沒有的都有了),不再需要
    規則式翻譯。EN 版維持 wiki。抓不到官方頁(太舊/斷線)退回
    wiki+規則翻譯。網頁 API 加 categoriesZh(官方版含英雄圖示),
    zh 模式優先渲染,計數列顯示「官方繁中原文」。
  - 解析要點:內容在 #patch-notes-container(SSR);token 掃描
    h2(段落:競技場/英雄/道具/大混戰,其餘忽略)→ h4(競技場式分類)
    / h3(一般對戰英雄)→ `<p><strong>條目</strong></p>`+`<li>`。
    ⚠️ 標籤都帶 style 屬性,regex 要 `[^>]*`。slug 兩種格式都試。
  - ⚠️ 官方 zh 行不可再過 translate_lines(含 Discord/Buff 等英文詞
    會被誤標 🔤),直接掛 linesZh。
  - 🔎 發現 Riot 兩個官方來源譯名會不一致:遊戲內「編鐘」vs
    官方 notes「調和之音」(巴德 Chimes)—— 專案標準:遊戲內字串優先。
  - **剩餘 🔤 只在 arena_balance(MapChanges)**:無官方中文,
    規則翻譯 68%;其餘計畫由 Claude 逐句翻譯建 overrides 對照檔
    (下一步,尚未做)。
- **2026-07-10**(字體調整 + 專有名詞來源確認):
  - 網頁加字體大小按鈕(A → A+ → A++ → A−,body zoom + localStorage)。
  - 「米普」加進 GLOSSARY(使用者確認的台服譯名);Chimes 官方譯名
    未確認,不猜,維持 🔤。
  - 🔎 **重大發現(未來方向)**:官方繁中 patch notes 可直接抓!
    `https://www.leagueoflegends.com/zh-tw/news/game-updates/`
    `league-of-legends-patch-26-13-notes`(26.4 起是這種 slug,
    26.2/26.3 是 `patch-26-2-notes`;清單可從
    `/zh-tw/news/tags/patch-notes/` 抓)。**SSR HTML**(不用跑 JS),
    內容在 `#patch-notes-container`,含米普/亞菲利歐等全部官方翻譯。
    需帶瀏覽器 User-Agent、follow_redirects(307)。
    → 若做「官方繁中 patch notes 解析」,規則式翻譯就退居備援;
    也可半自動比對官方繁中/wiki 英文建術語表。工程量中等,待排程。
- **2026-07-10**(大改版:規則式翻譯 + 一般對戰 + UI 強化):
  - **translate.py(新)**:規則式英→中翻譯。固定句型(changed to /
    increased to / reduced to / 「Label: A ⇒ B」)+ 台服術語表(~130 條,
    GLOSSARY)。**沒把握的整行保留英文 + 🔤 標記**,絕不輸出半中半英。
    實測覆蓋:MapChanges 技能行 68%、patch 條目 ~5 成(自由句多)。
    使用者之後回報缺的術語 → 加 GLOSSARY 即可。
    ⚠️ 「Tier: Gold ⇒ ...」語境 Gold=黃金非金幣,已特判。
  - **patch_notes 加 scope**:tool 改名 `patch_notes(scope, patch, query,
    locale)`,scope = arena/general/mayhem。一般對戰段落格式不同
    (`;{{ci|英雄}}` 開條目,parse_dl_section);Mayhem 段落與 Arena 同格式。
    一次抓頁三個 scope 一起快取(cache key `wiki_patch_V26.13`)。
    Mayhem 強化台服名接 cherry-augments.json(nameTRA 欄位,638 筆)。
  - **網頁**:全域深色/淺色切換(CSS 變數 + localStorage)、
    角色定位篩選(ddragon tags + cdragon 官方職業圖示
    `rcp-fe-lol-champion-details/.../role-icon-*.png`,注意該站擋 HEAD
    請求,要用 GET 驗證)、patch 分頁 scope 切換、footer 聯繫(GitHub
    only,使用者定案)+ Claude 協同聲明 + Riot 免責。
  - **流量統計**:環境變數 `GOATCOUNTER_CODE` 有設才在 home() 注入
    GoatCounter script;使用者要自己去 goatcounter.com 註冊拿 code,
    然後在 Render dashboard 設 env var(還沒做,等使用者)。
  - 驗收:92 tests(+10 translate);三 scope API + 角色篩選 + 中文行
    全部 node/HTTP 實測過。
- **2026-07-10**(中英雙版本 + 台服名 + 圖示):使用者要求「英文都要有
  對應中文,而且要台服官方譯名(不是機翻),英雄附圖示,做中英兩版本」。
  - **台服名來源(全部是遊戲內字串,不翻譯)**:英雄/裝備 = ddragon
    zh_TW(champion.json/item.json)、強化 = cdragon arena zh_tw、
    技能名 = ddragon **championFull.json**(en+zh 各 ~2MB,cache key
    `spell_names`)。變形英雄的複合技能名(en "Cunning Sweep /
    Sundering Slam" ↔ zh「暗襲/裂斬」)兩邊都按斜線切開按位置配對
    (champions.py `split_ability_names`)。
  - patch_notes 條目名比對用 `_name_key`(小寫去空白標點),解掉
    wiki "Hivemind" ↔ 遊戲 "Hive Mind"。**查不到就保留英文**:
    Juiced/Spellcraft/Final Form 等 V26.09 新強化不在 cdragon
    arena json(226 筆)裡;cherry-augments.json(638 筆)查證過是
    **Mayhem 專用**(ARAM_ 前綴),幫不上競技場。
  - 兩個 tool 都加 `locale`("zh_tw"/"en_us")。en 版把清理器的中文
    標注轉回英文(wikitext.py `translate_annotations_en`,和 _render
    的字樣要同步)。網頁 header 加全域「中/EN」切換,四個分頁的名稱
    /說明/表頭都跟著換;patch 分頁英雄條目附圖示,中文名可搜尋。
  - 🐛 **修掉一個潛伏 bug**:模板參數依 `|` 切割會切爛
    `[[File:xxx.png|20px|border]]` 這種帶管線的連結(Ryze/Mel/Zac
    的 pp type= 受害,中文版也是壞的)→ `_split_top_level` 追蹤
    [[ ]] 深度。另一個:en 轉換 regex 的括號要跳脫(半形字面括號)。
  - 驗收:82 tests(+9);API linesEn 全量掃描零殘留中文標注、
    node 雙語渲染四分頁全過;正式站部署後驗證(見下)。
- **2026-07-10**(競技場擴充第 4 項):新 tool `arena_patch_notes` +
  網頁「📋 Patch 改動」分頁(`/api/patch-notes?patch=`)。實作重點:
  - 資料源:各 patch 頁(V26.13 等)的 `== Arena ==` 段落,三層 bullet
    (分類→條目→「舊 ⇒ 新」),幾乎無模板,清理器直接沿用。
    ⚠️ wiki 有 `== Arena ===` 這種等號不對稱的標題,extract 已容錯。
  - 「最新 patch」不從 cdragon 版本推算(ddragon 16.x ≠ wiki V26.x
    兩套編號),改用 MediaWiki allpages(apprefix=V2)枚舉取最大;
    最新頁若沒有 Arena 段落自動往前找(最多 4 版)。
  - query 中文翻譯:英雄走 resolve_champion、強化走 arena 雙語索引、
    裝備新增 ddragon item.json 中英對照(cache key `item_names`)。
    「殞落之祭」→ Rite Of Ruin 驗證過;最新版沒改到時自動往回找
    最近一次改動(最多 8 版)。
  - **刻意不做**:不自動判定 buff/nerf(「冷卻 60⇒15」是好是壞看機制,
    亂標會錯),原樣呈現「舊 ⇒ 新」。
  - Arena/Patch history 子頁是 tabview(1st~5th launch),屬模式改版史;
    patch 頁另有 `ARAM: Mayhem` 段落 —— 未來 mayhem 可用同一套解析器。
  - 驗收:73 tests 全過(+6);MCP client 實測 6 tools、API latest/26.12
    正常、網頁 JS node 實跑(37 條目、過濾正常、無殘留模板)。
- **2026-07-10**(競技場擴充第 1 項):新 tool `arena_balance` + 網頁
  「⚔️ 競技場平衡」分頁(`/api/arena-balance`)上線。實作重點:
  - `wikitext.py`:模板清理器。語意都查過模板原始碼 ——
    `{{ap}}`=隨技能等級、`{{pp}}`=隨英雄等級、`{{rd|A|B}}`=近戰A/遠程B
    (Template:Range difference)、`{{ft|A|B}}`=兩種等價寫法取第一種
    (Template:FlipText)。策略:反覆化簡「最內層」{{...}}(實測巢狀
    最深 7 層大括號)。`{{tip|縮寫}}` 有中文對照表(er=效果半徑等)。
  - `arena_balance.py`:MapChanges/data/ar 有 587 條(453 英雄/123 裝備
    /11 符文,items/runes 也解析進快取備用)。條目 key 對 ddragon 名單
    做最長前綴比對分組,453/453 全中;唯一別名:wiki 的 "Nunu" →
    ddragon 的 "Nunu & Willump"(`_WIKI_NAME_ALIASES`)。技能標籤:
    Q/W/E/R 原樣、I/P→被動、純英雄名→整體、具名技能(Nidalee Prowl)原樣。
  - 基礎數值("ar" 區塊)併進 aram.py 同一次 wiki 抓取(cache key 不變,
    data 多一個 "ar" key);MapChanges 是獨立 cache key
    `wiki_mapchanges_ar`。兩源之一失敗仍出另一半結果,各自註明。
  - 驗收:67 tests 全過(+22 wikitext、+8 arena_balance);HTTP 模式
    真 MCP client 呼叫 5 tools、API 200(152/173 英雄有調整)、
    網頁 JS 用 node + DOM stub 實跑 renderArena(152 卡片、過濾、
    粗體轉換、無殘留 {{模板}})。**尚未 push / 部署**。
  - 已知取捨:技能調整原文是英文 wiki(無中文源),數字與模板標注
    已中文化;`{{ap|40 to 60}}%` 會排成「40−60(隨技能等級)%」,
    % 落在括號後,可接受。
- **2026-07-09**(session 1 續,Phase 3):Claude Desktop 是
  **Microsoft Store 版**,設定檔在
  `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json`
  (不是 %APPDATA%\Claude),已寫入 mcpServers(uv.exe 絕對路徑)。
  ⚠️ 踩坑:PS 5.1 的 ConvertFrom-Json 編碼問題會弄壞這個檔,改 JSON 一律用 Python。
  GitHub repo:https://github.com/NewJeans0722/lol-mode-mcp(已 push)。
  ⚠️ FastMCP Cloud 首次部署 failed:它以 `fastmcp run 檔案:物件` 方式
  載入 entrypoint、不會 pip install 本專案,src/ 下的 server.py 相對匯入
  直接炸。解法:根目錄加部署入口 `server.py`(sys.path 塞 src/ 再
  re-export `mcp`),**dashboard 的 entrypoint 要填 `server.py:mcp`**。
  用 `uv run --with fastmcp fastmcp inspect server.py:mcp` 驗證過
  (fastmcp 3.x runner 可載入官方 SDK 的 FastMCP 物件)。
- **2026-07-10**(Phase 3 完成):FastMCP Cloud 修好 entrypoint 與
  fastmcp 依賴後部署成功,但強制 Horizon 帳號驗證(401),公開存取
  要付費 → **放棄,改用 Render 免費方案**(`render.yaml` blueprint,
  push 自動部署)。Render 上首戰 **421 Misdirected Request**:官方 SDK
  的 DNS rebinding 防護預設只放行 localhost Host header,雲端反代必炸
  → 以 `TransportSecuritySettings(enable_dns_rebinding_protection=False)`
  關閉(公開資料服務,安全上可接受)。上線後全流程驗收通過
  (握手 1.1s、各 tool 0.2~2.1s),README 填入正式網址,打 v0.1.0 tag。
  Claude Desktop(Store 版)設定已寫好,使用者待實測 connector。

- **2026-07-09**(session 1):讀 brief → 驗證三個資料源(見上)→
  完成骨架 + 全部 4 tools + resource + 快取/錯誤處理 + 28 tests →
  stdio/HTTP 雙 transport 用真 MCP client 驗證 → 修 3 個迭代問題
  (patch 字串修剪、%i:...% 圖示標記清理、資料檔移進套件)+
  SDK env var 踩坑修正。使用者補充指示:競技場資料正確性優先、
  ARAM 也重要、輸出排版要好看、日誌要寫好。
