#!/bin/bash
# 双击运行：装成 macOS LaunchAgent，服务常驻，之后不用再点启动。
# 撤销：双击 uninstall-autostart.command
cd "$(dirname "$0")" || exit 1
DIR="$(pwd)"; PLIST="$HOME/Library/LaunchAgents/com.xhs-vault.serve.plist"; PY="$(command -v python3)"
mkdir -p "$HOME/Library/LaunchAgents" "$DIR/logs"
cat > "$PLIST" <<PLEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.xhs-vault.serve</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$DIR/serve.py</string></array>
  <key>WorkingDirectory</key><string>$DIR</string>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$DIR/logs/serve.log</string>
  <key>StandardErrorPath</key><string>$DIR/logs/serve.log</string>
</dict></plist>
PLEOF
launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST" && echo "已装上开机自启。"
for _ in $(seq 1 40); do curl -s -m 2 http://127.0.0.1:8899/api/health >/dev/null 2>&1 && break; sleep 0.5; done
curl -s http://127.0.0.1:8899/api/health; echo
echo; echo "看板：http://127.0.0.1:8899/dashboard.html"; echo "日志：$DIR/logs/serve.log"
read -r -p "按回车关闭…" _
