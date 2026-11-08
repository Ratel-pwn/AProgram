@echo off
setlocal
pushd "%~dp0"
cargo build --release --locked
set "aprogram_build_exit=%ERRORLEVEL%"
popd
exit /b %aprogram_build_exit%
