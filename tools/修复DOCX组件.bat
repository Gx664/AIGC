@echo off
chcp 65001 >nul
title AIGC 检测工具箱 - 修复 DOCX 解析组件
setlocal

rem ============================================================
rem  修复：上传 .docx 时提示 "No module named 'exceptions'"
rem
rem  原因：安装时把依赖名写成了 docx，pip 于是装到 PyPI 上
rem        2011 年的 Python 2 版本（单文件 docx.py），它在
rem        Python 3 下无法使用。正确的包名是 python-docx。
rem
rem  用法：把本文件复制到「AIGC 检测工具箱」的安装根目录
rem        （即同时含有 app 和 runtime 两个文件夹的那一层），
rem        双击运行即可。装完重新打开软件。
rem ============================================================

set "PY=%~dp0runtime\python\python.exe"

echo ============================================================
echo   AIGC 检测工具箱 - 修复 DOCX / PDF 解析组件
echo ============================================================
echo.

if not exist "%PY%" (
    echo [错误] 没找到便携运行时：
    echo        %PY%
    echo.
    echo        请把本脚本放到安装根目录（与 app、runtime 同级）再运行。
    echo.
    pause
    exit /b 1
)

echo 运行时位置: %PY%
echo.

echo [1/3] 卸载装错的旧组件 docx ...
"%PY%" -m pip uninstall -y docx
echo.

echo [2/3] 安装正确的组件 python-docx ...
"%PY%" -m pip install python-docx -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo.
    echo [提示] 上面的源装不上，换官方源再试一次 ...
    "%PY%" -m pip install python-docx
)
echo.

echo [3/3] 校验 ...
"%PY%" -c "import docx, docx.opc.constants; print('OK  -  python-docx 已可用')"
if errorlevel 1 (
    echo.
    echo [失败] 组件仍不可用。请把上面的完整输出发给作者。
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   修复完成，重新打开软件即可上传 .docx 文件。
echo ============================================================
echo.
pause
