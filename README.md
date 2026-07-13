# lol-mode-mcp

LoL「模式限定」資料的 MCP server + 查詢網站 —— 競技場(Arena)海克斯強化、競技場/ARAM 每英雄平衡、逐 patch 改動(競技場/一般對戰/ARAM Mayhem)。中英雙語,中文名稱一律採**台服官方譯名**(遊戲內字串,非機器翻譯)。

市面上的 LoL 工具幾乎都只做英雄/裝備,模式資料沒人整合,這個 server 補上這塊。

## 提供的能力

| 類型 | 名稱 | 說明 |
|---|---|---|
| tool | `get_augment(query, locale, mode)` | 模糊搜尋海克斯強化(競技場/ARAM Mayhem 兩套分開查,同名互相提示) |
| tool | `list_augments(tier, locale, mode)` | 依稀有度列出強化清單(mode 選競技場或 ARAM Mayhem) |
| tool | `arena_balance(champion, locale)` | 英雄本 patch 的競技場專屬平衡:基礎數值加成 + 逐技能改動(技能用台服名) |
| tool | `patch_notes(scope, patch, query, locale)` | 逐 patch 改動清單(舊值 ⇒ 新值);scope 可選競技場/一般對戰/ARAM Mayhem,query 可用中文名 |
| tool | `aram_balance(champion)` | 英雄本 patch 的 ARAM 平衡數值,標明增益/削弱 |
| tool | `mayhem_balance(champion)` | ARAM: Mayhem 數值(延伸功能,暫未支援) |
| tool | `mode_mechanics(mode)` | 模式機制說明:強化選取規則、回合表、貴賓投票、Mayhem 進度(含「機率/英雄限定名單官方未公開」的誠實聲明) |
| resource | `lol-mode://mode-mechanics` | 同上機制說明的 JSON 原文 |

改動說明的中文採**規則式翻譯**(固定句型 + 台服術語對照表),沒把握的句子保留英文並標 🔤 —— 寧可給原文也不亂翻。

## 查詢網站(給人看的)

<https://lol.zhongqqq.win/> —— 五個分頁:海克斯圖鑑(競技場/ARAM Mayhem 雙圖鑑、稀有度篩選)、競技場平衡、ARAM 平衡表(可排序)、Patch 改動(範圍/版本切換)、模式機制。支援中/EN 切換、深色/淺色主題、角色定位篩選(官方職業圖示)、原畫背景、中文名搜尋。

## 朋友使用方式(不用安裝任何東西)

1. 打開 Claude(桌面版/網頁版/手機版皆可)
2. **設定(Settings)→ 連接器(Connectors)→ 新增自訂連接器(Add custom connector)**
3. 名稱隨意填(例如 `LoL 模式資料`),網址貼上:

   ```
   https://lol.zhongqqq.win/mcp
   ```

   > 💡 伺服器閒置一段時間會休眠,第一個問題可能要等 30~60 秒喚醒,之後就是正常速度。
   > (原生網址 `https://lol-mode-mcp.onrender.com/mcp` 亦可用。)

4. 儲存後開新對話,直接問:「灼燒煉金那個強化在做什麼」、「悟空的 ARAM 有被削嗎」

## 自行架設

用 [uv](https://docs.astral.sh/uv/) + Python 3.10+ 可直接跑(`uv sync && uv run lol-mode-mcp`);雲端部署設定在 `render.yaml`,push 即自動部署。

## 資料來源與致謝

- 競技場/Mayhem 強化與職業圖示:[CommunityDragon](https://communitydragon.org/) —— 感謝社群維護的遊戲資料鏡像(patch 剛更新時可能有延遲)
- 平衡數值與逐 patch 改動:[League of Legends Wiki](https://wiki.leagueoflegends.com/)(內容授權 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/))
- 英雄/裝備/技能台服譯名:Riot [Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon)

## 聯繫與協作聲明

- 📮 作者:[GitHub @NewJeans0722](https://github.com/NewJeans0722);問題與建議請開 [Issue](https://github.com/NewJeans0722/lol-mode-mcp/issues)
- 🤖 本專案與 [Claude](https://claude.com/claude-code)(Anthropic)協同開發:架構、程式碼與測試由 Claude Code 輔助完成,需求、範圍決策與驗收由作者主導

## 免責聲明

lol-mode-mcp 並非 Riot Games 官方出品,亦未獲得 Riot Games 認可或贊助。League of Legends 及 Riot Games 為 Riot Games, Inc. 之商標或註冊商標。

lol-mode-mcp isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

## License

[MIT](LICENSE)(程式碼);引用的資料內容依各來源授權(見上)。
