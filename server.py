"""FastMCP Cloud 部署入口。

FastMCP Cloud 以「檔案路徑」載入 entrypoint(等同 `fastmcp run server.py:mcp`),
不會先把本專案 pip install 成套件 —— 所以這裡手動把 src/ 加進 sys.path,
讓 lol_mode_mcp 能以正常套件身分被匯入(套件內部的相對匯入才不會壞)。

本機開發請照舊用 console script:`uv run lol-mode-mcp`(見 README)。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from lol_mode_mcp.server import mcp  # noqa: E402  (re-export for the cloud runner)

if __name__ == "__main__":
    from lol_mode_mcp.server import main
    main()
