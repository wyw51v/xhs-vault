#!/bin/bash
PLIST="$HOME/Library/LaunchAgents/com.xhs-vault.serve.plist"
launchctl unload "$PLIST" 2>/dev/null; rm -f "$PLIST"; pkill -f "serve.py" 2>/dev/null
echo "已卸载开机自启，服务已停。"
read -r -p "按回车关闭…" _
