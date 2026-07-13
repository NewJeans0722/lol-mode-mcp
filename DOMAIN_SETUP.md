# 網域與架站筆記(zhongqqq.win)

> 給自己與未來的 Claude session:目前的上線架構、怎麼設起來的、
> 之後要加子網域或除錯時看這份。設定於 2026-07(patch 16.13 期間)。

## 現況總覽

```
訪客 ──▶ Cloudflare(CDN/代理,免費)──▶ Render(免費方案,美國)──▶ app
                │ 台北等節點就近快取                    │ FastMCP + 網站 + API
                └ 網域 zhongqqq.win 在 Cloudflare Registrar 買+管理
```

- **網站(給人看)**:https://lol.zhongqqq.win/
- **MCP(給 Claude 連)**:https://lol.zhongqqq.win/mcp
- **舊網址仍可用**:https://lol-mode-mcp.onrender.com/(Render 原生網址,備援)
- **主網域 zhongqqq.win**(apex)目前**未指向任何服務**,保留給日後作品集/個人主頁

## 各家角色與帳號

| 服務 | 用途 | 費用 |
|---|---|---|
| Cloudflare Registrar | 買 + 管理網域 zhongqqq.win | ~US$ 幾塊/年(.win 成本價) |
| Cloudflare(同帳號) | DNS + CDN 代理(橘雲) | 免費 |
| Render | 跑 app(容器) | 免費方案 |
| GitHub NewJeans0722/lol-mode-mcp | 原始碼;push 觸發 Render 自動部署 | 免費 |

因為網域是在 Cloudflare 官網買的,**nameserver 自動就是 Cloudflare 的,不用改**,
網域一買好 Overview 就是 Active。

## DNS 記錄(Cloudflare → DNS 分頁)

| Type | Name | Target | Proxy |
|---|---|---|---|
| CNAME | `lol` | `lol-mode-mcp.onrender.com` | 橘雲(Proxied) |

- Cloudflare **SSL/TLS → Overview 模式 = Full**(Render 有正式憑證,選 Full 才不報錯)。

## ⚠️ 踩過的雷 / 設定訣竅

1. **先灰雲、再橘雲**:直接開橘雲(Proxied)Render 常驗證不過(DNS 查
   到的是 Cloudflare IP、看不到 CNAME 指向自己)。正確順序:
   加記錄時**先灰雲(DNS only)→ 回 Render 按 Verify、等憑證發好
   (綠勾)→ 再把雲點成橘色**開加速 → SSL 設 Full。
2. 加記錄是在 Cloudflare 的 **DNS** 分頁,不是 Overview(Overview 只是總覽)。
3. DNS 生效可能要幾分鐘~最久 24 小時,通常很快。

## 之後要做的事

- **再開一個子網域**(例:作品集 `zhongqqq.win` 或 `me.zhongqqq.win`):
  在該服務(Render/其他)加自訂網域拿到 target → Cloudflare DNS 加一筆
  CNAME/A、橘雲 → 同樣 SSL Full。子網域無限、免費。
- **apex(zhongqqq.win 本身)指向服務**:Cloudflare 支援 CNAME flattening,
  在 apex 加 CNAME 即可(Name 填 `@`)。
- **自訂 email**(`你@zhongqqq.win`):Cloudflare **Email → Email Routing**
  免費轉信到 Gmail,不用另外架 mail server。

## 效能備註(冷啟動 = 最大的「卡」)

Cloudflare 只加速「可快取 / 邊緣命中」的請求,**喚醒 Render 的第一個請求
還是得穿過去**;Render 免費版閒置 15 分鐘休眠、冷啟動 30~60 秒,
Cloudflare 治不了。防休眠方案由弱到強:

1. **GitHub Actions keepalive**(現有,`.github/workflows/keepalive.yml`,
   每 10 分鐘 ping onrender origin)。⚠️ 免費版排程常延遲/跳過,不夠可靠,
   所以偶爾還是會睡著 —— 當備援用。
2. **外部監控 ping(推薦的免費解)**:註冊 **UptimeRobot**(免費),
   新增一個 HTTP monitor,URL 填 **`https://lol-mode-mcp.onrender.com/`**
   (打 origin、不經 Cloudflare 才會真的喚醒),間隔 **5 分鐘**。
   比 GitHub Actions 可靠很多,基本上能讓它一直醒著。順便還能收宕機通知。
3. **根治(要花錢)**:Render 付費 **Starter $7/月**,不休眠、永遠即時。
   若哪天真的有穩定流量再考慮。

> 注意:UptimeRobot 要 ping **onrender.com origin**,不要 ping
> `lol.zhongqqq.win`(那個經 Cloudflare,可能命中快取而沒喚醒後端)。

- 版本更新流程見 `UPDATE_SOP.md`;開發/部署細節見 `README.dev.md`(本地)。
