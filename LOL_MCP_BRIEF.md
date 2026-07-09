# 專案交辦:lol-mode-mcp — LoL 模式資料 MCP server
(整份貼給 Claude Code。我是 MCP 初學者,請邊做邊解釋每個決定。)

## 專案目標

做一個 MCP server,提供 LoL「模式限定」資料 —— 競技場(Arena)海克斯強化、
ARAM / ARAM: Mayhem 的每英雄平衡數值、模式機制說明。市面上的 LoL 工具
幾乎都只做英雄/裝備,模式資料沒人整合,這是這個專案的價值。

最終要部署成 remote MCP server:朋友只要在 Claude 設定的 Connectors
貼一個公開網址就能用,不用安裝任何東西;我 push 到 GitHub 就自動
重新部署,朋友端什麼都不用做。

## 技術規格

- Python 3.10+,官方 MCP SDK 的 FastMCP,httpx,uv 管理專案。
- transport 雙軌:本機開發/測試用 stdio;正式部署用 streamable-http
  (remote MCP 標準),用環境變數切換,第一天就照這個結構寫。
- 工具必須 stateless:雲端 serverless 不保證跨請求狀態,
  快取要能在任何一次請求中隨時重建。
- pyproject.toml 設 console script 進入點(例如 `lol-mode-mcp`)
  方便本機執行;正式發布走雲端部署(見「發布與朋友使用」)。

## 資料源(先抓回來看結構,再寫程式)

1. 競技場強化(整理版,首選):
   https://raw.communitydragon.org/latest/cdragon/arena/en_us.json
   - 繁中:把 en_us 換成 zh_tw 試試;若無此 locale 再退回英文。
   - 這是社群專案 CommunityDragon,patch 剛更新時可能延遲,
     程式必須優雅處理「抓不到 / 查無此強化」。
2. 競技場強化(原始檔,備用):
   https://raw.communitydragon.org/latest/plugins/rcp-be-lol-game-data/global/default/v1/cherry-augments.json
3. ARAM 每英雄平衡數值(傷害/承傷/治療/護盾/技能急速等乘數):
   官方 Data Dragon 沒有這些。結構化來源是 LoL Wiki 的資料模組
   (wiki.leagueoflegends.com 的 Module:ChampionData/data 與
   Template:map_changes/data/aram)。請先研究最穩的抓法
   (MediaWiki API 取 wikitext 再解析,或抓渲染頁面解析表格),
   跟我討論後再實作。這是全案最難的部分,放 Phase 2。
4. ARAM: Mayhem 有自己獨立的一組英雄數值與強化 —— 作為延伸目標,
   先把介面留好(tool 可先回「暫未支援」)。

授權:CommunityDragon 是社群專案、LoL Wiki 內容是 CC BY-SA,
README 必須標明資料來源與致謝;LICENSE 用 MIT。
README 也要放 Riot 的免責聲明(本專案非 Riot Games 官方出品)。

## 要提供的 MCP 能力

tools:
- get_augment(query: str, locale: str = "zh_tw") -> str
  模糊搜尋海克斯強化(接受中英文名或關鍵字),回傳名稱、稀有度
  (白銀/黃金/稜彩)、完整效果說明。找不到時列出最接近的候選。
- list_augments(tier: str = "all", locale: str = "zh_tw") -> str
  依稀有度列出強化清單(名稱 + 一句效果摘要)。
- aram_balance(champion: str) -> str
  回傳該英雄本 patch 的 ARAM 乘數,標明哪些是增益哪些是削弱;
  英雄名接受中英文。查無資料要說清楚是「無調整」還是「查詢失敗」。
- mayhem_balance(champion: str) -> str(延伸,可先留 stub)

resource:
- mode-mechanics:一份我之後會手工校訂的 JSON(先放骨架),
  內容是嚎哭深淵光環、競技場基本規則等機制說明,掛成 MCP resource。
  請解釋 resource 和 tool 的差別,以及 Claude Desktop 怎麼讀到它。

## 工程要求

- 啟動時抓一次資料並快取在記憶體(附時間戳),過期(例如 12 小時)
  重抓;抓失敗時退回上次快取並在回覆中註明資料可能過期。
- 所有 httpx 呼叫要有 timeout 與錯誤處理;回覆一律對「人類可讀」友善。
- 用 `uv run mcp dev server.py`(MCP Inspector)測試每個 tool。
- 寫最小限度的單元測試(至少:強化搜尋命中/未命中、英雄名正規化)。

## 分階段(每階段完成先停下來給我驗收,再進下一階段)

Phase 1(今天):專案骨架 + get_augment + list_augments 跑通,
  接上我的 Claude Desktop,我問「灼燒煉金那個強化在做什麼」能得到答案。
  過程中逐段解釋程式碼。
Phase 2:aram_balance(含 wiki 解析)+ 錯誤處理強化 + 測試。
  完成後對整個 codebase 做一次完整 review 與重構建議。
Phase 3:發布 —— 推 GitHub、接上 FastMCP Cloud 取得公開網址、
  切換 streamable-http 並實際用 Claude 的 custom connector 連上驗證;
  README(含朋友版教學:在 Claude 設定貼網址的步驟)、LICENSE、
  致謝、打 v0.1.0 tag。

## 發布與朋友使用(README 要照這個寫)

部署平台:FastMCP Cloud(免費個人方案)。流程:推 GitHub → 在
FastMCP Cloud 連結這個 repo → 取得公開網址(https://...);之後每次
push 自動重新部署,朋友端不需任何動作。

朋友使用方式:在 Claude 的 設定 → Connectors → 新增自訂連接器,
貼上公開網址即可(桌面/網頁/手機通用)。README 要附這段的
step-by-step 截圖說明位置。

安全性:本專案只提供公開遊戲資料、不碰任何秘密,先不做驗證;
若之後想限定朋友使用,再加簡單的 API key 檢查(X-API-Key header)。

備援方案:若 FastMCP Cloud 不合用,退回 Cloudflare Workers
(免費每日 10 萬請求,但需改寫 TypeScript)—— 先不要走這條,
遇到問題時和我討論再決定。

## 互動方式

- 把我當新手:每個階段先講計畫、再動手,關鍵程式碼逐段解釋「為什麼」。
- 遇到資料源和預期不符(欄位改名、zh_tw 不存在等),先展示實際抓到的
  JSON 給我看,和我討論再改設計,不要沉默地繞過。
- 每個 Phase 之間我會 /clear,所以重要決定請寫進 repo 的 NOTES.md,
  下個 session 開場先讀它。
