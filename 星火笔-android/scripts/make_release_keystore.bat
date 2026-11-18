@echo off
REM 生成 release 签名（keystore + keystore.properties），供 build.gradle 的 signingConfigs.release 使用。
REM 依赖 JDK（Android Studio 自带 JBR，或系统 java 在 PATH）。
REM 首次构建 release 前运行一次；生成后可反复使用同一签名升级安装（务必妥善备份 release.keystore）。
setlocal
cd /d "%~dp0..\app"

set KS=release.keystore
set ALIAS=xinghuobi
set PWD=xinghuobi2026
set DNAME=CN=XinghuoPen,O=XinghuoPen,L=CN,ST=CN,C=CN

if exist "%KS%" (
    echo [i] %KS% 已存在，跳过生成（如需重建请先删除）。
) else (
    where keytool >nul 2>nul
    if errorlevel 1 (
        echo [x] 找不到 keytool，请先安装 JDK（Android Studio 自带 JBR，或在系统环境 PATH 里加入 java）。
        exit /b 1
    )
    keytool -genkeypair -v -keystore "%KS%" -alias %ALIAS% -keyalg RSA -keysize 2048 -validity 36500 ^
        -storepass %PWD% -keypass %PWD% -dname "%DNAME%"
    if errorlevel 1 exit /b 1
    echo [i] 已生成 %KS%（有效期 100 年；密码 %PWD%；请妥善备份此文件用于后续版本升级签名）
)

echo storeFile=app/release.keystore> keystore.properties
echo storePassword=%PWD%>> keystore.properties
echo keyAlias=%ALIAS%>> keystore.properties
echo keyPassword=%PWD%>> keystore.properties
REM 注意：build.gradle 的 signingConfigs 对属性值做了 .trim() 兜底，
REM 避免 echo 写入带来的行尾空格导致 "keystore password was incorrect"。
echo [i] keystore.properties 已写入（app/ 下；已被 .gitignore 排除，不入库）
echo [ok] 签名就绪。现在可用 build_apk.bat 构建带正式签名的 APK。
endlocal
