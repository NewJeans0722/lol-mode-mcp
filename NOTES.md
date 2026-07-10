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
2. **投票機制 =「Vote Phase / Guests of Honor(貴賓)」— 資料在 Arena 主頁**
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
   **顯示一律用 `desc`**,解不出的佔位符標「?」並附說明。
4. **`dataValues` 是長度 7 的陣列**,部分強化可升級所以各 index 值不同
   (例:全能之魂 2/3/4/5/6/7 種龍魂)。不猜哪個 index,
   把相異值依序用「/」串接呈現。7 個 index 的確切語意未查證。
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

1. **(要你動手)** `src/lol_mode_mcp/data/mode_mechanics.json` 裡的
   TODO 段落需要你手工校訂(深淵光環數值、競技場規則細節)。
2. **(要你動手)** 裝 Claude Desktop 後,把 README「本機開發」段的
   json 貼進 `claude_desktop_config.json` 實測。
3. Phase 3 部署時:README 的 `<部署後的公開網址>` 佔位、截圖、
   GitHub repo 網址(http_util.py 的 User-Agent 裡也有佔位)要補。
4. 可考慮:mayhem 資料源(wiki 是否新增 mayhem 模組)、
   list_augments 加英文 locale 的標題在地化(目前少量中文字樣寫死)。

## 日誌

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
