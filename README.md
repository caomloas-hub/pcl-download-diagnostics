# PCL Download Doctor

Windows 下 PCL 下载入口的**诊断与公告阻塞恢复工具**，Python 3.11+，仅使用标准库。

**先试最简单的方法：Alt+F4 正常关闭 PCL，然后重新打开。**
在已验证的 2.14.0.0 中，“悲报 / PCL 不再提供 MC 下载功能”可能是
编号 230 的公告模态框，唯一按钮触发更新，并不代表当前可执行文件已失去下载功能。
PCL 展示公告前通常已经保存已读编号，因此重启可能足够。

## 支持范围

- 已核对 PCL **2.14.0.0**，SHA-256：
  `77fbc26a13abf725dbd26038cba023224c2ce5518f3ee9c4608acb2274d753f0`。
- 只处理匹配的缓存公告 230；未知 EXE 拒绝修复。
- **不能恢复新版已经移除或编译禁用的下载代码**，不是通用解锁器。
- 不修改 EXE，不降级，不屏蔽域名，不关闭证书验证、正版认证或自动更新，
  不读取账号、令牌、游戏日志，不包含或下载 Minecraft/PCL 程序。
- PCL 是 Java 版启动器，本工具不添加基岩版下载能力。

## 使用

在普通用户终端运行，不需要管理员权限：

```powershell
python pcl_download_doctor.py inspect --exe "D:\Games\PCL\Plain Craft Launcher 2.exe"
```

如果诊断匹配且重启后仍遇到同一个公告，先正常关闭 PCL：

```powershell
python pcl_download_doctor.py repair --exe "D:\Games\PCL\Plain Craft Launcher 2.exe"
```

修复仅在当前公告编号小于 230 时，将
`HKEY_CURRENT_USER\Software\PCL\HintNotice` 写为字符串 `230`。
这会将截至 230 的公告标记为已读，不屏蔽将来的公告。编号已达到或超过 230 时不写入。
修改前将该值的原始存在状态、类型和值备份到
`%LOCALAPPDATA%\PCLDownloadDoctor\backups`，不导出整个注册表。

重新打开 PCL，选择一个未安装版本，验证下载完成。修复命令不自动启动游戏。

回滚（先关闭 PCL，使用修复输出的具体备份路径）：

```powershell
python pcl_download_doctor.py restore --exe "D:\Games\PCL\Plain Craft Launcher 2.exe" --backup "C:\path\notice-ID.json"
```

如果公告状态后来发生变化，回滚拒绝覆盖。注册表状态属于当前 Windows 用户，
同一用户的多个 PCL 安装可能共享这个值。备份包含本地状态，不应提交到 GitHub。

可通过 `--notice` 指定缓存路径；默认 `%TEMP%\PCL\Cache\Notice.json`。
脚本不会执行公告中的 URL、actions 或其他指令。

## 验证

```powershell
python -m unittest -v
```

测试覆盖未知程序拒绝、公告校验、已读幂等、备份和回滚、原始类型恢复、
运行中拒绝修改、后续状态冲突与备份目标校验。
测试使用临时文件和模拟注册表，不修改真实 PCL 配置。

人工验证环境：Windows、PCL 2.14.0.0；重启后成功重新进入下载流程。
完整安装结果见 [验证记录](VALIDATION.md)。

## 来源与边界

这是独立编写的故障诊断工具，与 PCL、Mojang、Microsoft 无隶属关系。
不分发上游源码、程序、游戏资产或私人日志。MIT 许可证仅适用于本仓库代码。

- [PCL 官方源码](https://github.com/Meloong-Git/PCL)
- [PCL 当前下载页面源码](https://github.com/Meloong-Git/PCL/blob/main/Plain%20Craft%20Launcher%202/Pages/PageDownload/PageDownloadInstall.xaml.vb)
- [PCL 当前网络模块](https://github.com/Meloong-Git/PCL/blob/main/Plain%20Craft%20Launcher%202/Modules/ModSecret.vb)

上游 main 会继续变化，不能把旧版公告诊断结果套用到新版。
将来如需扩展支持，应先检查对应版本行为、记录哈希并补充测试，不要盲目放宽校验。
