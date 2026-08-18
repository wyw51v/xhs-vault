#!/bin/bash
# 双击运行：启动本地服务并打开看板。
# 浏览器不能自己启动进程（安全边界），所以这个文件就是那一次点击。
cd "$(dirname "$0")" || exit 1
URL="http://127.0.0.1:8899/dashboard.html"

if curl -s -m 2 http://127.0.0.1:8899/api/health >/dev/null 2>&1; then
  echo "服务已在运行，直接打开看板。"; open "$URL"
  echo; echo "（可关掉此窗口。停服务：pkill -f 'serve.py'）"; exit 0
fi

echo "正在启动…"
python3 serve.py &
SRV=$!
for _ in $(seq 1 40); do
  if curl -s -m 2 http://127.0.0.1:8899/api/health >/dev/null 2>&1; then
    open "$URL"; echo; echo "看板已打开：$URL"
    echo "关掉此窗口或按 Ctrl-C 会停掉服务。"; wait $SRV; exit 0
  fi
  sleep 0.5
done
echo "启动超时。手动排查：cd '$(pwd)' && python3 serve.py"
read -r -p "按回车关闭…" _
