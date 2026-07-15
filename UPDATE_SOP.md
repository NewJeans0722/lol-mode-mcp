# 版本更新 SOP(標準作業流程)

> 新 patch 上線後照這份跑一遍,就能一次把該處理的都處理完,
> 不用等使用者一個一個回報。歷史踩雷與判斷都收在 `NOTES.md`。

## 為什麼多數東西會自動更新

資料都是「即時抓最新來源 + 12 小時快取」:競技場強化、英雄/裝備/技能
名與圖示、patch 改動、ARAM 數值 —— 來源一更新,重新部署(或快取過期)
後就是新版。**需要人工的只有「翻譯對照檔」和「季節輪替的機制」。**

## 一鍵自檢

```bash
uv run python scripts/check_update.py
```

它會抓最新資料,逐項檢查過往的雷,把要動手的列清楚:

| # | 檢查 | 全綠代表 | 黃色時做什麼 |
|---|---|---|---|
| 1 | 版本一致性 | ddragon/cdragon 同版 | 某來源還沒跟上,等幾小時再跑 |
| 2 | 競技場強化說明 | 無 `@` 漏出 | `@` 漏出=formatting.py 要修;「(依遊戲內數值)」可接受 |
| 3 | 競技場技能改動 | 100% 可翻 | 列出的行補進 `data/mapchanges_zh.json` |
| 4 | Mayhem 強化說明 | 100% 完整中文 | 列出的強化補進 `data/mayhem_zh.json` |
| 5 | 對照檔時效 | key 全對得上 | 列出的舊 key 可刪(強化被移除/改名) |
| 6 | 機制/貴賓 | (永遠提醒) | 大改版才需要,見下方 |

**額外手動檢查(patch 改動)**:開網站或 MCP tool 查最新版,
確認英雄名稱是否獨立顯示、沒黏在一起。若黏住 = Riot 改了官方筆記
的 HTML 結構(上次 V26.14 把 `<p><strong>` 改成 `<p>` 純文字),
修 `official_notes.py` 的 `_TOKEN_RE` 和 group 對應(<60 行)。

## 補翻譯的規矩(正確性優先,沿用既有標準)

1. **數值一律以英文 wiki 為準**(Mayhem 尤其:官方遊戲字串的
   `_summary` 是「簡短摘要」會砍掉數值,不可用;要嘛人工翻英文全文,
   要嘛用 `_tooltipdescription` 全文)。
2. **專有名詞必查官方台服名,不要用猜的**:
   - 英雄/裝備/技能名 → Data Dragon(`champion.json`/`item.json`/
     `championFull.json`,locale=zh_TW)。曾整批猜錯:雄心之鋼≠紅寶石之心、
     日炎聖盾、巴米灰燼、虛偽光彩、探索者護腕、蒐集者。
   - 符文 → `runesReforged.json`(zh_TW):征服者/致命節奏/靈魂收割…
   - 強化名 → cdragon `cherry-augments.json` 的 `nameTRA`。
3. **術語用專案統一詞彙**(見 `translate.py` 的 `GLOSSARY`):護盾、
   適應之力、技能急速、施放判定、擊殺參與、額外(bonus)、最大生命…
4. **對照檔 key**:`mapchanges_zh.json` = 去 `**`/`*` 後的英文原句;
   `mayhem_zh.json` = 英文強化名(穩定,不受改字影響)。
5. **翻不出/沒把握的**保留英文(規則翻譯會自動標 🔤),不要硬翻。

## 貴賓/機制(第 6 項,季節大改版才需要)

貴賓每賽季整批輪替,**LoL Wiki 的貴賓表會落後一整輪**(踩過雷)。
大改版時以**官方繁中 patch notes 的「特別嘉賓」段落**為準,核對並改寫
`data/mode_mechanics.json`(guest 結構:nameEn/nameZh/rule/effect)。
順手比對回合獎勵表、Mayhem 進度解鎖。用 `official_notes.get_official_zh`
可抓官方繁中原文。

## 收尾(每次都做)

```bash
uv run pytest -q          # 全過
# (改了說明排版才需要)本機起 server 用 127.0.0.1 抽查幾個
git add -A && git commit && git push   # push 後 Render 自動部署
```

部署後開網站 Ctrl+F5,確認頂部版本標示是新的。抽查幾個新/改動的強化
確認中文與數值正確(這一步很值得——曾靠抽查抓到官方摘要砍數值的問題)。
