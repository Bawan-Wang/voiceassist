#!/bin/bash

# Photoframe Runner Script
# 這個腳本用來執行photoframe應用程式

# 設定工作目錄
WORKSPACE_DIR="/home/jh-pi/workspace/photoframe"
PYTHON_SCRIPT="$WORKSPACE_DIR/main.py"

# 檢查Python腳本是否存在
if [ ! -f "$PYTHON_SCRIPT" ]; then
    echo "錯誤: 找不到Python腳本 $PYTHON_SCRIPT"
    exit 1
fi

# 檢查Python是否安裝
if ! command -v python3 &> /dev/null; then
    echo "錯誤: 找不到Python3，請先安裝Python3"
    exit 1
fi

# 切換到工作目錄
cd "$WORKSPACE_DIR" || {
    echo "錯誤: 無法切換到工作目錄 $WORKSPACE_DIR"
    exit 1
}

echo "正在啟動Photoframe..."
echo "工作目錄: $WORKSPACE_DIR"
echo "Python腳本: $PYTHON_SCRIPT"
echo "----------------------------------------"

# 執行Python腳本
python3 "$PYTHON_SCRIPT"

# 檢查執行結果
if [ $? -eq 0 ]; then
    echo "Photoframe執行完成"
else
    echo "Photoframe執行時發生錯誤 (退出碼: $?)"
    exit 1
fi
