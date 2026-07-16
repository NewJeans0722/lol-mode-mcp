"""lol-mode-mcp:LoL 模式限定資料的 MCP server。

架構說明(給未來的自己):
- FastMCP 是官方 MCP SDK 的高階 API:用 decorator 把普通函式
  變成 MCP tool/resource,型別註記自動變成 schema。
- tool 函式都是同步的 —— FastMCP 會把同步函式丟進 thread pool 執行,
  不會卡住事件迴圈;對這種「抓 JSON + 查表」的工作量足夠了。
- transport 雙軌:
    stdio           本機開發(Claude Desktop 直接 spawn 這個程式)
    streamable-http 雲端部署(remote MCP 標準,朋友貼網址即用)
  用環境變數 MCP_TRANSPORT 切換,預設 stdio。
- 所有狀態只有「可隨時重建的記憶體快取」,符合 serverless 的
  stateless 要求(見 cache.py)。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from .aram import do_aram_balance
from .mayhem_augments import (do_get_mayhem_augment, do_list_mayhem_augments,
                              do_mayhem_balance)
from .arena import do_get_augment, do_list_augments
from .arena_balance import do_arena_balance
from .mechanics import do_mode_mechanics
from .patch_notes import do_patch_notes

# logging 一律走 stderr:stdio transport 下 stdout 是 MCP 協定通道,
# 印任何雜訊到 stdout 都會弄壞協定。
logging.basicConfig(
    level=os.environ.get("LOL_MCP_LOG_LEVEL", "INFO"),
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("lol_mode_mcp")

# stateless_http=True:每個 HTTP 請求獨立處理、不要求 session 黏著,
# 這是部署到 serverless(FastMCP Cloud)必須的模式。
# host/port 可由環境變數 FASTMCP_HOST / FASTMCP_PORT 覆寫(SDK 內建)。
mcp = FastMCP(
    "lol-mode-mcp",
    instructions=(
        "提供 LoL 模式限定資料:競技場(Arena)海克斯強化查詢、"
        "ARAM 每英雄平衡數值。所有查詢支援中文(繁體)與英文名稱。"
    ),
    stateless_http=True,
    # SDK 預設的 DNS rebinding 防護只放行 localhost 的 Host header,
    # 部署在雲端(Render 等)會對正常請求回 421 Misdirected Request。
    # 這防護是保護「跑在本機的 HTTP server」不被惡意網頁跨站打,
    # 對公開雲端服務(只供公開遊戲資料、無任何秘密)關掉是安全的。
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False),
)


_MAYHEM_MODES = ("mayhem", "aram", "aram_mayhem", "大混戰", "kiwi")


@mcp.tool()
def get_augment(query: str, locale: str = "zh_tw", mode: str = "arena") -> str:
    """模糊搜尋海克斯強化,回傳名稱、稀有度與完整效果說明。

    競技場與 ARAM Mayhem 是兩套不同的強化(同名者數值/效果可能不同),
    用 mode 區分;查到同名時會提示另一模式也有。

    Args:
        query: 強化名稱或關鍵字,中英文皆可(例:「地獄三頭犬」、"Cerberus"、「灼燒」)。
        locale: 回覆語言,"zh_tw"(預設)或 "en_us"。
        mode: "arena"(競技場,預設)或 "mayhem"(ARAM Mayhem)。
    """
    logger.info("tool get_augment(query=%r, locale=%r, mode=%r)",
                query, locale, mode)
    if mode.strip().lower() in _MAYHEM_MODES:
        return do_get_mayhem_augment(query, locale)
    return do_get_augment(query, locale)


@mcp.tool()
def list_augments(tier: str = "all", locale: str = "zh_tw",
                  mode: str = "arena") -> str:
    """依稀有度列出海克斯強化清單(名稱 + 一句效果摘要)。

    Args:
        tier: "all"(預設)/ "silver" 白銀 / "gold" 黃金 / "prismatic" 稜彩
              / "special" 特殊(僅競技場有)。中文別名也可以。
        locale: 回覆語言,"zh_tw"(預設)或 "en_us"。
        mode: "arena"(競技場,預設)或 "mayhem"(ARAM Mayhem)。
    """
    logger.info("tool list_augments(tier=%r, locale=%r, mode=%r)",
                tier, locale, mode)
    if mode.strip().lower() in _MAYHEM_MODES:
        return do_list_mayhem_augments(tier, locale)
    return do_list_augments(tier, locale)


@mcp.tool()
def aram_balance(champion: str) -> str:
    """查詢英雄本 patch 的 ARAM(嚎哭深淵)平衡數值,標明增益與削弱。

    涵蓋:造成傷害/承受傷害/治療/護盾/技能急速/攻擊速度/韌性/能量回復。
    「無調整」與「查詢失敗」會明確區分。

    Args:
        champion: 英雄名稱,中英文皆可(例:「悟空」、"Wukong"、「犽宿」)。
    """
    logger.info("tool aram_balance(champion=%r)", champion)
    return do_aram_balance(champion)


@mcp.tool()
def arena_balance(champion: str, locale: str = "zh_tw") -> str:
    """查詢英雄本 patch 的競技場(Arena)平衡調整,標明增益與削弱。

    涵蓋:基礎數值加成(生命/攻擊/護甲/攻速的基礎值與成長值)
    與逐技能改動(冷卻、傷害、係數等,取自英文 wiki)。
    中文版技能名使用台服官方譯名。「無調整」與「查詢失敗」會明確區分。

    Args:
        champion: 英雄名稱,中英文皆可(例:「阿卡莉」、"Akali")。
        locale: 回覆語言,"zh_tw"(預設)或 "en_us"。
    """
    logger.info("tool arena_balance(champion=%r, locale=%r)", champion, locale)
    return do_arena_balance(champion, locale)


@mcp.tool()
def patch_notes(scope: str = "arena", patch: str = "latest", query: str = "",
                locale: str = "zh_tw") -> str:
    """查詢某一版 patch 的改動清單(舊值 ⇒ 新值),即「相對上一版的 nerf/buff」。

    範圍可選競技場(強化/英雄/裝備/貴賓)、一般對戰(召喚峽谷的英雄/裝備/
    召喚師技能/符文/野怪)或 ARAM: Mayhem。中文版名稱使用台服官方譯名,
    說明採規則式翻譯(翻不出的保留英文並標 🔤)。

    Args:
        scope: "arena"(競技場,預設)/ "general"(一般對戰)/ "mayhem"。
        patch: "latest"(預設,最新版)或版本號(例:「26.13」、"V26.12")。
        query: 選填,只看特定對象的改動,中英文皆可
               (例:「殞落之祭」、「伊莉絲」、"Eclipse")。
        locale: 回覆語言,"zh_tw"(預設)或 "en_us"。
    """
    logger.info("tool patch_notes(scope=%r, patch=%r, query=%r, locale=%r)",
                scope, patch, query, locale)
    return do_patch_notes(scope, patch, query, locale)


@mcp.tool()
def mode_mechanics(mode: str = "arena") -> str:
    """查詢模式機制說明:強化選取規則、回合獎勵表、貴賓投票、Mayhem 進度等。

    手工整理的中文摘要。注意:強化的英雄限定名單與出現機率
    在 Riot 伺服器端、官方未公開,回覆內含誠實聲明。

    Args:
        mode: "arena"(競技場,預設)/ "aram" / "mayhem"。中文別名也可以。
    """
    logger.info("tool mode_mechanics(mode=%r)", mode)
    return do_mode_mechanics(mode)


@mcp.tool()
def mayhem_balance(champion: str) -> str:
    """查詢英雄在 ARAM: Mayhem 的平衡:一般 ARAM 補正 + Mayhem 專屬覆寫。

    Mayhem 疊加在一般 ARAM 補正之上,兩層都會列出;
    專屬覆寫僅部分英雄有(取自英文 wiki,規則式翻譯)。

    Args:
        champion: 英雄名稱,中英文皆可(例:「巴德」、"Bard")。
    """
    logger.info("tool mayhem_balance(champion=%r)", champion)
    return do_mayhem_balance(champion)


# ---------------------------------------------------------------- resource
# resource 和 tool 的差別:
#   tool     = 模型「主動呼叫」的函式,適合查詢/計算(有參數、有邏輯)。
#   resource = 掛在固定 URI 上的「唯讀內容」,像一份文件;
#              客戶端(或使用者)把它附加到對話的 context 裡,
#              模型不需要呼叫任何東西就能讀到。
# mode-mechanics 是手工校訂的靜態說明文件,天生適合當 resource。
# 在 Claude Desktop:對話輸入框的「+」(附加)選單 → 選這個 MCP server
# → 會列出下面這個 resource,點了就把 JSON 內容放進對話。

# 放在套件目錄內,無論從 repo 直跑還是打包安裝都讀得到
_MECHANICS_PATH = Path(__file__).resolve().parent / "data" / "mode_mechanics.json"


@mcp.resource("lol-mode://mode-mechanics",
              name="mode-mechanics",
              description="LoL 模式機制說明(嚎哭深淵光環、競技場規則等,手工校訂)",
              mime_type="application/json")
def mode_mechanics() -> str:
    try:
        return _MECHANICS_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("mode_mechanics.json unreadable: %s", exc)
        return json.dumps({"error": f"mode_mechanics.json 讀取失敗:{exc}"},
                          ensure_ascii=False)


# ---------------------------------------------------------------- 網頁介面
# 同一個 HTTP server 順便掛查詢網頁(給人用)與 JSON API(給網頁的 JS 用);
# MCP 客戶端仍走 /mcp,互不干擾。stdio 模式下這些路由不存在。
from .web import (api_aram, api_arena_balance, api_augments,  # noqa: E402
                  api_backgrounds, api_mayhem_augments, api_mechanics,
                  api_patch_notes, api_save_facing, home)

mcp.custom_route("/", methods=["GET"])(home)
mcp.custom_route("/api/augments", methods=["GET"])(api_augments)
mcp.custom_route("/api/aram", methods=["GET"])(api_aram)
mcp.custom_route("/api/arena-balance", methods=["GET"])(api_arena_balance)
mcp.custom_route("/api/patch-notes", methods=["GET"])(api_patch_notes)
mcp.custom_route("/api/backgrounds", methods=["GET"])(api_backgrounds)
mcp.custom_route("/api/mayhem-augments", methods=["GET"])(api_mayhem_augments)
mcp.custom_route("/api/mechanics", methods=["GET"])(api_mechanics)
mcp.custom_route("/api/save-facing", methods=["POST"])(api_save_facing)


def main() -> None:
    transport = os.environ.get("MCP_TRANSPORT", "stdio").strip().lower()
    if transport in ("http", "streamable-http", "streamable_http"):
        # 開機暖身:背景先抓齊資料源、算好 API payload(arena-balance
        # 全量翻譯實測要數秒),讓第一個訪客不用等
        import threading
        from .web import warmup
        threading.Thread(target=warmup, daemon=True, name="warmup").start()
        # 注意:這版官方 SDK 的 FastMCP() 建構子會把預設 host/port 明確
        # 塞進 Settings,導致 FASTMCP_* 環境變數被蓋掉 —— 所以自己讀。
        # PORT 是各家雲端平台的慣例;HTTP 模式要綁 0.0.0.0 外面才連得到。
        mcp.settings.host = os.environ.get("FASTMCP_HOST", "0.0.0.0")
        mcp.settings.port = int(os.environ.get("PORT")
                                or os.environ.get("FASTMCP_PORT") or 8000)
        logger.info("starting with streamable-http transport "
                    "(host=%s port=%s)", mcp.settings.host, mcp.settings.port)
        mcp.run(transport="streamable-http")
    else:
        logger.info("starting with stdio transport")
        mcp.run()  # 預設 stdio


if __name__ == "__main__":
    main()
