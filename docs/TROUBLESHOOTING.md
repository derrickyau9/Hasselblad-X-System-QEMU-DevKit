# Troubleshooting / 故障排查

| Symptom / 现象 | Action / 处理 |
| --- | --- |
| Unknown firmware / 不支持固件 | Use the exact tested official X2D II versions in the compatibility record. Renaming a file does not change compatibility. 使用已验证的官方固件，改文件名不会改变兼容性。 |
| Checksum failure / 校验失败 | Retry runtime setup; incomplete `.part` downloads are replaced. 校验失败时重新安装环境即可重试下载。 |
| Download interrupted / 下载中断 | Run setup again. Verified completed archives and extracted components are reused. 重新安装会复用已校验完成的部分。 |
| UI startup timeout / 启动超时 | Open logs folder; inspect `console.log` and `qemu.log`. Ensure sufficient RAM and close other heavy emulators. 查看日志并确认内存充足。 |
| Blank preview / 空白预览 | Stop and start the guest; inspect the first compositor/UI error in the console log. 停止后重新启动，检查日志中的首个 UI 错误。 |
| Slow UI / 界面较慢 | This is ARM64 TCG plus software graphics on x86-64. Host GPU hardware acceleration is not enabled. 当前使用跨架构 CPU 模拟及软件渲染。 |
| Some menu actions do nothing / 菜单部分操作无反应 | Most physical camera services are mocked. This is expected for capture, AF and hardware operations. 拍摄、对焦等实机服务没有实现。 |
| Another session owns the guest / 其他会话占用 | Stop its DevKit window. The lock is an OS lock, not a stale-file test; deleting `session.lock` is unnecessary. 关闭占用的窗口，无需删除锁文件。 |
| Compiler not found / 找不到编译器 | Select the NDK root containing `toolchains/llvm/prebuilt/windows-x86_64/bin/clang.exe`. |
| Runtime location changed / 运行目录变化 | Restore the runtime path or use a fresh data directory and re-import. Save your workspace edits first. 恢复原路径，或备份开发文件后使用新的数据目录。 |
| Windows blocks an unsigned EXE / 未签名程序提示 | The portable build is unsigned. Verify SHA256SUMS and source, or build locally. 发布包未签名，可核对哈希及源码，或自行构建。 |

## Report a problem

Include the DevKit version, firmware **version**, Windows version, failure stage
and a short relevant log excerpt. Review logs for local paths and personal data
before posting. Do not upload complete firmware, credentials or camera dumps.

反馈时提供 DevKit 版本、固件版本、Windows 版本、出错步骤及相关日志片段。
发布前检查本地路径和个人信息；不要上传整份固件或凭据。
