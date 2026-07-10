# NOTES.md — 開發日誌與重要決定

> 給下一個 session(和未來的自己):開場先讀這份。
> 專案需求原文在 `LOL_MCP_BRIEF.md`。

## 目前狀態(2026-07-09)

**Phase 1~3 全部完成,已上線:`https://lol-mode-mcp.onrender.com/mcp`(v0.1.0)**

下一步候選(和使用者討論中):tool 回覆附上海克斯強化圖示。
圖源已驗證:CommunityDragon 直接掛遊戲資產,
`https://raw.communitydragon.org/latest/game/` + JSON 裡的 `iconLarge` 路徑
(例:`assets/ux/cherry/augments/icons/cerberus_large.png` → HTTP 200)。
呈現方式二選一:(a) 文字附連結(便宜);(b) MCP ImageContent 內嵌
base64 圖(Claude 會直接顯示圖卡,較慢較肥)。

- ✅ 專案骨架(uv + src layout + console script `lol-mode-mcp`)
- ✅ `get_augment` / `list_augments`(競技場強化,中英雙語搜尋)
- ✅ `aram_balance`(LoL Wiki Lua 模組解析,含英雄名中英正規化)
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
  champions.py   英雄名正規化(Data Dragon en_US + zh_TW)
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
