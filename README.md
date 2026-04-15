
<div align="center">

# 🚀 Shell 执行器
[![版本](https://img.shields.io/badge/版本-v2.1.0-blue)](#)
[![作者](https://img.shields.io/badge/作者-懒大猫-orange)](#)
[![框架平台](https://img.shields.io/badge/框架平台-AstrBot-blue)](#)

> 支持持久会话，在聊天中安全、持久化地执行 Shell 命令 —— 像操作本地终端一样自然

</div>

## 📖 简介

**Shell 执行器** 是一款专为 AstrBot 设计的插件，允许 **授权用户** 在聊天环境中执行 Shell 命令。  
不同于一次性执行，它提供了 **持久化的交互式会话** —— 每个用户拥有独立的 Shell 会话，环境变量、工作目录、命令历史都会保持，甚至支持需要交互的命令（如 `apt install`、`rm -i`、密码输入等）。

### ✨ 核心亮点

| 特性 | 说明 |
| :--- | :--- |
| 🔐 **严格的授权控制** | 仅配置中的授权用户可使用，其他人无权执行任何命令 |
| 🧠 **持久化会话** | 每个用户独立会话，`cd`、`export` 等操作在后续命令中依然生效 |
| 💬 **交互式命令支持** | 自动识别 `[y/n]`、`password:` 等提示符，等待用户继续输入 |
| 🛡️ **危险命令拦截** | 内置危险命令黑名单（`rm -rf`、`mkfs`、`shutdown` 等），可自定义 |
| ⚙️ **WebUI 配置** | 所有配置项均在 AstrBot WebUI 中完成，**无需重启**即可生效 |
| 📦 **即装即用** | 支持通过 WebUI 链接直接安装，也可手动复制文件安装 |
| 🧹 **会话重置** | 使用 `/shell reset` 随时重置当前会话 |
| 📊 **智能输出截断** | 可配置最大输出长度，防止刷屏 |
| 🛑 **命令中断** | 使用 `/shell stop` 或 `/ctrl c` 中断卡死的命令 |
| ⌨️ **完整控制键支持** | 通过 `/ctrl` 发送任意 `Ctrl+字母` 组合键 |

---

## 📦 安装

### 方法一：WebUI 链接安装（推荐，无需重启）

1. 打开 AstrBot WebUI，进入 **插件商店**
2. 点击右下角 **+** ，**通过链接安装**
3. 输入以下安装链接：
   ```
   https://github.com/landamao/abpl_shdo
   ```
4. 确认安装，插件会自动下载并启用 —— **无需重启 AstrBot** 🎉

### 方法二：手动安装

1. 下载插件源码，得到以下文件：
   - `main.py`
   - `_conf_schema.json`
   - `requirements.txt`
   - `metadata.yaml`
2. 在 `AstrBot/data/plugins/` 目录下创建文件夹 `shell执行器`
3. 将文件放入 `shell执行器` 目录下
4. **重启 AstrBot** 完成加载

---

## ⚙️ 配置说明

在 AstrBot WebUI 的 **插件配置** 页面，可以实时修改以下配置（保存后立即生效，无需重启）：

| 配置项 | 类型 | 默认值 | 说明 |
| :--- | :--- | :--- | :--- |
| 👤 **授权用户** | `list` | `[]` | 允许使用插件的用户ID列表（如 QQ号、平台UID）。**留空则所有人都无法使用** |
| ⏱️ **超时时间** | `int` | `120` | 单个命令的最大执行时间（秒），超时自动发送 Ctrl+C 中断 |
| 📝 **记录日志** | `bool` | `false` | 是否打印详细的命令执行日志（用于调试） |
| 📂 **工作目录** | `string` | `插件目录/工作目录` | 所有命令执行的起始工作目录（绝对路径） |
| 🚫 **危险命令** | `list` | 见下方 | 禁止执行的命令模式列表（支持部分匹配） |
| 📏 **最大输出长度** | `int` | `2000` | 单次回复的最大字符数，超出截断（<20 表示不限制） |

> **危险命令默认值**（可根据需要修改或清空）：
> ```json
> [
>   "rm -rf", "mkfs", "dd", "shutdown", "reboot", "poweroff", "halt",
>   "chmod 777", "chmod -R 777", "chown -R", ":(){ :|:& };:",
>   "> /dev/sda", "mkfs.ext4", "dd if=/dev/zero"
> ]
> ```

---

## 🎮 使用方法

### 核心命令

| 命令 | 作用 | 示例 |
| :--- | :--- | :--- |
| `/shell <命令>` 或 `/sh <命令>` | 执行 Shell 命令或响应交互输入 | `/shell ls -la` |
| `/shell reset` | 重置当前用户的会话（清空环境、工作目录重置） | `/shell reset` |
| `/shell stop` | 中断当前正在执行的命令（相当于 Ctrl+C） | `/shell stop` |
| `/ctrl <字母>` | 向当前会话发送 `Ctrl+字母` 组合键 | `/ctrl c` 或 `/ctrl d` |

### 详细使用示例

#### 1️⃣ 基本命令执行
```bash
# 第一次执行，自动创建会话
/shell pwd
> ✅ 执行完成：
> /app/data/plugins/shell执行器/工作目录
> 退出码: 0

# 切换目录并查看
/shell cd /tmp
/shell pwd
> ✅ 执行完成：
> /tmp
```

#### 2️⃣ 环境变量保持
```bash
/shell export MY_NAME="AstrBot"
/shell echo $MY_NAME
> ✅ 执行完成：
> AstrBot
```

#### 3️⃣ 交互式命令（自动等待输入）
```bash
/shell apt install sl
> 🔄 需要继续输入：
> Do you want to continue? [Y/n]
> 请发送下一步输入

# 用户发送 y 作为响应
/shell y
> ✅ 执行完成：
> ... 安装过程输出 ...
> 退出码: 0
```

#### 4️⃣ 中断卡死的命令
```bash
# 执行一个无限循环
/shell while true; do echo "loop"; sleep 1; done
# 输出会不断刷新... 此时发送中断
/shell stop
> 🛑 已发送中断信号
> loop
> loop
> ...
> 退出码: 130   # 130 表示被 SIGINT 中断
```

#### 5️⃣ 发送控制键
```bash
# 发送 Ctrl+C 中断（效果同 /shell stop）
/ctrl c

# 发送 Ctrl+D 退出当前 shell（会结束会话，下次自动重建）
/ctrl d
> ⌨️ 已发送 Ctrl+D
> (无输出)
```

#### 6️⃣ 重置会话
```bash
/shell reset
> ♻️ 会话已重置
# 之后所有环境变量、工作目录恢复初始状态
```

### 交互提示符自动识别

插件内置正则匹配以下常见模式（不区分大小写）：
- `[y/n]`、`(y/N)`、`[Yes/no]`
- `password:`、`Press any key`、`Press ENTER`
- `更多`、`是否继续`、`请输入`
- `Enter your choice`、`Choice:`、`Select:`
- 以 `?` 结尾的行（如 `rm: remove file 'test'?`）

匹配到后会进入 **等待输入模式**，用户的下一条 `/shell` 内容会作为输入发送给当前进程。

---

## 🧠 工作原理

1. **授权检查**：只有 `授权用户` 列表中的用户才能触发插件。
2. **会话管理**：每个用户第一次执行 `/shell` 时会创建一个真正的 `bash` 子进程（使用 `pexpect` 模拟终端）。
3. **命令发送**：后续所有 `/shell` 命令都发送到该用户的同一会话中，因此 `cd`、`export`、`alias` 等会持续生效。
4. **交互检测**：每次命令输出后，插件会扫描是否存在交互提示符，若存在则进入 **等待输入模式**，下一次用户消息会直接作为输入发送给正在运行的进程。
5. **超时与中断**：命令执行超过配置时间后自动发送 `Ctrl+C` 中断；用户也可主动使用 `/shell stop` 或 `/ctrl c`。
6. **控制键发送**：`/ctrl` 命令允许发送任意 `Ctrl+字母` 组合键，实现更精细的终端控制。

---

## ⚠️ 注意事项

- **安全性**：请谨慎授权用户，授权用户拥有完全等同于运行 AstrBot 主机的 Shell 权限。建议使用 Docker 或虚拟环境隔离运行 AstrBot。
- **并发限制**：不同用户的会话相互隔离，同一用户在同一时间只有一个活跃命令（交互等待期间无法执行新命令）。
- **日志隐私**：开启 `记录日志` 后，所有命令及输出会写入 AstrBot 日志文件，请注意不要泄露敏感信息。
- **平台适配**：用户ID格式取决于消息平台（QQ 号、微信ID、钉钉ID等），请确保 `授权用户` 中填写的是正确的平台标识。
- **Windows 支持**：插件底层使用 `/bin/bash`，仅支持 Linux / macOS / WSL。Windows 原生环境请使用 WSL 或 Docker 部署 AstrBot。

---

## ❓ 常见问题

<details>
<summary><b>Q: 提示“你没有权限”怎么办？</b></summary>

请在 WebUI 插件配置中，将你的用户ID（如 QQ号）添加到 `授权用户` 列表中，保存即可。  
> 如何获取自己的用户ID？让机器人随便发一条消息，查看后台日志中的 `sender_id` 字段。
</details>

<details>
<summary><b>Q: 命令执行后没有任何输出？</b></summary>

可能原因：
- 命令本身无输出（如 `cd`、`export`）
- 超时时间过短导致命令被中断
- 输出被截断（检查 `最大输出长度` 配置）

尝试执行 `echo "test"` 验证基本功能。
</details>

<details>
<summary><b>Q: 如何退出交互等待模式？</b></summary>

- 发送 `/shell stop` 取消等待并中断命令
- 发送 `/shell reset` 重置整个会话
</details>

<details>
<summary><b>Q: 为什么我的 `cd` 命令没有生效？</b></summary>

检查路径是否存在及权限。插件本身不会拦截 `cd`。如果仍然无效，请尝试重置会话后重新执行。
</details>

<details>
<summary><b>Q: 超时后命令还在后台运行吗？</b></summary>

超时后插件会发送 `Ctrl+C` 中断前台进程，但如果命令启动了后台子进程（如 `&` 或 `nohup`），这些子进程可能仍在运行。建议使用 `kill` 等命令手动清理。
</details>

<details>
<summary><b>Q: 如何查看当前会话的 PID？</b></summary>

在会话中执行 `echo $$` 即可获取 shell 进程的 PID。
</details>

---

## 📝 更新日志

### v2.1.0 (当前)
- ✅ 新增 `/shell stop` 命令，可中断正在执行的命令
- ✅ 新增 `/ctrl <字母>` 命令，支持发送任意 Ctrl 组合键
- ✅ 命令超时后自动发送 `Ctrl+C` 而非直接终止
- ✅ 插件卸载/重载时自动清理所有用户会话
- ✅ 优化超时提示信息

### v2.0.0
- ✅ 持久化交互式会话，支持 `cd`、`export` 等状态保持
- ✅ 自动识别交互提示符，支持多轮输入
---

## 🤝 贡献与反馈

项目地址：[https://github.com/landamao/abpl_shdo](https://github.com/landamao/abpl_shdo)  
欢迎提交 Issue 或 PR，让插件变得更好用！
