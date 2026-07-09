# lol-mode-mcp

LoL「模式限定」資料的 MCP server —— 競技場(Arena)海克斯強化、ARAM 每英雄平衡數值、模式機制說明。中英文都能查。

市面上的 LoL 工具幾乎都只做英雄/裝備,模式資料沒人整合,這個 server 補上這塊。

## 提供的能力

| 類型 | 名稱 | 說明 |
|---|---|---|
| tool | `get_augment(query, locale)` | 模糊搜尋競技場海克斯強化(中英文名或關鍵字),回傳稀有度與完整效果 |
| tool | `list_augments(tier, locale)` | 依稀有度(白銀/黃金/稜彩/特殊)列出強化清單 |
| tool | `aram_balance(champion)` | 英雄本 patch 的 ARAM 平衡數值,標明增益/削弱 |
| tool | `mayhem_balance(champion)` | ARAM: Mayhem 數值(延伸功能,暫未支援) |
| resource | `lol-mode://mode-mechanics` | 手工校訂的模式機制說明(深淵光環、競技場規則) |

## 朋友使用方式(不用安裝任何東西)

1. 打開 Claude(桌面版/網頁版/手機版皆可)
2. **設定(Settings)→ 連接器(Connectors)→ 新增自訂連接器(Add custom connector)**
3. 名稱隨意填(例如 `LoL 模式資料`),網址貼上:

   ```
   https://<部署後的公開網址>/mcp
   ```
   <!-- TODO(Phase 3): 部署到 FastMCP Cloud 後把真實網址填進來,並補上設定畫面截圖 -->

4. 儲存後開新對話,直接問:「灼燒煉金那個強化在做什麼」、「悟空的 ARAM 有被削嗎」

## 本機開發

需要 [uv](https://docs.astral.sh/uv/) 與 Python 3.10+。

```bash
uv sync                                 # 安裝依賴
uv run pytest                           # 跑測試
uv run mcp dev src/lol_mode_mcp/server.py   # MCP Inspector 互動測試
uv run lol-mode-mcp                     # 直接啟動(stdio)
```

接上自己的 Claude Desktop(`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "lol-mode-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "C:/Users/zhong/Desktop/LOL_MCP", "lol-mode-mcp"]
    }
  }
}
```

## 部署(FastMCP Cloud)

1. push 到 GitHub([NewJeans0722/lol-mode-mcp](https://github.com/NewJeans0722/lol-mode-mcp))
2. 在 [FastMCP Cloud](https://fastmcp.cloud) 連結 repo,entrypoint 指向 `src/lol_mode_mcp/server.py` 的 `mcp` 物件
3. 取得公開網址;之後每次 push 自動重新部署,朋友端不需任何動作

環境變數:

| 變數 | 預設 | 說明 |
|---|---|---|
| `MCP_TRANSPORT` | `stdio` | 設 `streamable-http` 走 remote MCP |
| `FASTMCP_HOST` / `FASTMCP_PORT` | `127.0.0.1` / `8000` | HTTP 模式的監聽位址 |
| `LOL_MCP_CACHE_TTL` | `43200`(12 小時) | 資料快取秒數 |
| `LOL_MCP_LOG_LEVEL` | `INFO` | 日誌等級(輸出到 stderr) |

安全性:本專案只提供公開遊戲資料、不碰任何秘密,目前不做驗證。

## 資料來源與致謝

- 競技場強化:[CommunityDragon](https://communitydragon.org/) —— 感謝社群維護的遊戲資料鏡像(patch 剛更新時可能有延遲)
- ARAM 平衡數值與英雄資料模組:[League of Legends Wiki](https://wiki.leagueoflegends.com/)(內容授權 [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/))
- 英雄名稱(中英對照):Riot [Data Dragon](https://developer.riotgames.com/docs/lol#data-dragon)

## 免責聲明

lol-mode-mcp 並非 Riot Games 官方出品,亦未獲得 Riot Games 認可或贊助。League of Legends 及 Riot Games 為 Riot Games, Inc. 之商標或註冊商標。

lol-mode-mcp isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.

## License

[MIT](LICENSE)(程式碼);引用的資料內容依各來源授權(見上)。
