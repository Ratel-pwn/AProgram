# AProgram

AProgram 是 Windows 软件组启动器。为办公、游戏等场景配置应用，之后可以从系统托盘直接切换环境。切换时，AProgram 会启动目标组新增的应用，向离开当前组的应用发出关闭请求，并保留两组共用的应用。

## 使用

1. 打开 `aprogram.exe`，新建软件组。
2. 将 `.exe` 或 `.lnk` 拖入组内。单击应用切换它是否参与组操作，双击单独启动。
3. 右键单击系统托盘图标并选择软件组。左键单击托盘图标可恢复主窗口。

通过「设置与导入」选择旧版 AProgram 的目录，可导入 `software_groups.json` 和 `settings.json`。新版配置保存在 `%LOCALAPPDATA%\AProgram\state.json`。

## 从源码构建

在 Windows x64 上安装 Rust MSVC 工具链、Visual Studio C++ Build Tools 和 Windows SDK。Release 构建需要 SDK 中的 `fxc.exe`。请在 Visual Studio 开发者终端运行以下命令，或将环境变量 `GPUI_FXC_PATH` 指向本机的 `fxc.exe`。

```powershell
.\build.bat
.\target\release\aprogram.exe
```

Rust 入口位于 [src/main.rs](src/main.rs)，主窗口由 [GPUI](https://github.com/zed-industries/zed/tree/main/crates/gpui) 渲染。仓库里的 [main.py](main.py) 是旧版入口。[重构规格](docs/superpowers/specs/2026-11-08-rust-gpui-launcher-design.md)

本项目采用 [GNU AGPL v3](LICENSE)。
