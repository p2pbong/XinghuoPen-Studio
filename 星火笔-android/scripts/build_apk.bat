@echo off
REM 构建星火笔安卓版 APK（debug 或 release）。
REM 前置：Android Studio（含 JDK/Android SDK）+ Python 3.8+（Chaquopy 构建用，可从 PATH 找到或改 buildPython）。
REM
REM   1) 先运行 scripts\make_release_keystore.bat 生成 release 签名（只跑一次，长期复用）；
REM   2) 用 Android Studio 打开本目录（自动配置 Gradle 与 SDK），或在本目录执行：
REM      gradlew assembleRelease       构建正式签名 APK（app\build\outputs\apk\release\）
REM      gradlew assembleDebug         构建调试 APK（可直接安装测试）
setlocal
cd /d "%~dp0.."

echo [i] 目录：%CD%
echo [i] 推荐方式：用 Android Studio 打开本目录 → Build → Generate Signed Bundle/APK
echo      （Android Studio 会自动下载 Gradle 与依赖，首次构建需联网，耗时较长）
echo [i] 命令行方式（已装 gradle 时）：gradlew assembleDebug ^| assembleRelease
echo [i] 产物：app\build\outputs\apk\debug\app-debug.apk 或 app\build\outputs\apk\release\app-release.apk
echo [i] 检查签名：apksigner verify --print-certs app-release.apk
endlocal
