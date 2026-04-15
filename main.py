import asyncio
import os
import re
import time
from typing import Tuple, Any

import pexpect
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.all import AstrBotConfig, logger, Context, Star, Reply, Plain

class 交互式Shell会话:
    """持久化 Shell 会话，支持交互式命令和环境变量保持"""

    # 常见交互提示符的正则（可自行扩展）
    交互正则列表 = [
        r'\[y/n\]', r'\(y/n\)', r'\[Y/n\]', r'\[y/N\]',
        r'yes/no', r'\(yes/no\)', r'\[Yes/no\]',
        r'password:', r'Press any key', r'Press ENTER',
        r'更多', r'\[More\]', r'是否继续', r'请输入',
        r'Enter your choice', r'Choice:', r'Select:',
        r'confirm', r'Continue\?', r'Proceed\?',
        r'\?$',               # 以问号结尾（如 rm: remove file 'x'?）
        r'\(y/N\)', r'\(Y/n\)',
    ]
    交互正则 = re.compile('|'.join(交互正则列表), re.IGNORECASE)

    def __init__(self, 工作目录: str, 超时时间: int = 30, 记录日志: bool = False):
        self.超时时间 = 超时时间
        self.记录日志 = 记录日志
        self.info(f"[会话] 正在创建交互式 Shell 会话，工作目录: {工作目录}, 超时时间: {超时时间}秒")
        # 启动 bash，分配伪终端
        self.shell进程 = pexpect.spawn('/bin/bash', encoding='utf-8', echo=False)
        self.info(f"[会话] spawn bash 进程，PID: {self.shell进程.pid}")
        # 设置一个不会与普通输出混淆的提示符标记
        self.提示符标记 = '<<<PYTHON_SHELL_PROMPT>>>'
        self.shell进程.sendline(f'PS1="{self.提示符标记}"')
        self.info(f"[会话] 已发送 PS1 设置命令，提示符标记: {self.提示符标记}")
        # 等待第一个提示符出现，确保 shell 就绪
        self.shell进程.expect(self.提示符标记, timeout=5)
        self.info("[会话] 收到首个提示符，shell 已就绪")
        self.shell进程.sendline(f'cd "{工作目录}"')
        self.shell进程.expect(self.提示符标记, timeout=self.超时时间)
        self.info(f"[会话] 已切换工作目录至: {工作目录}")
        self.等待输入 = False   # 是否正在等待用户补充输入
        self.info("[会话] Shell 会话初始化完成")

    @staticmethod
    def 去命令回显(output: str, command: str) -> str:
        """去掉命令自身的回显行"""
        lines = output.splitlines()
        if lines and lines[0].strip() == command.strip():
            return '\n'.join(lines[1:])
        return output

    def send_interrupt(self) -> str:
        """
        向 shell 进程发送 Ctrl+C (SIGINT) 中断当前命令。
        采用非阻塞读取，立即返回，不再等待提示符。
        """
        self.info("[会话] 正在发送 Ctrl+C 中断信号")
        if not self.is_alive():
            self.warning("[会话] 进程已终止，无法发送中断信号")
            return ""

        # 发送中断信号
        self.shell进程.sendcontrol('c')
        time.sleep(0.1)  # 短暂让进程处理信号

        输出缓存 = ""
        try:
            # 循环读取当前所有立即可用的数据，直到无数据可读
            while True:
                data = self.shell进程.read_nonblocking(size=1024, timeout=0.1)
                if data:
                    输出缓存 += data
                else:
                    break
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            self.warning("[会话] 进程在中断后意外终止")

        # 清理 ANSI 转义码
        清理的输出 = self.过滤ANSI转义(输出缓存)
        self.info(f"[会话] 中断后立即读取到 {len(清理的输出)} 字节数据")
        return 清理的输出.strip()
    def _send_command_sync(self, command: str) -> Tuple[str, bool, bool, int | None]:
        """
        同步发送命令或用户输入，轮询读取输出直到：
        - 出现自定义 shell 提示符 → 命令正常结束，并获取退出码
        - 出现交互提示符 → 需要用户输入
        - 连续多次无新输出且无提示符 → 也认为需要输入（兜底）
        - 总超时 → 强制结束并发送中断信号
        返回 (输出内容, 是否仍需等待输入, 是否出错/超时, 退出码)
        """
        # 记录完整命令（不截断）
        self.info(f"[命令执行] 开始处理命令/输入，原始内容: {command}")
        if not self.等待输入:
            self.info(f"[命令执行] 作为新命令发送: {command}")
            self.shell进程.sendline(command)
        else:
            self.info(f"[命令执行] 作为交互响应发送: {command}")
            self.shell进程.sendline(command)
            self.等待输入 = False

        输出缓存 = ""
        最后输出长度 = 0
        无新输出计数 = 0
        开始时间 = time.time()
        轮询次数 = 0

        while time.time() - 开始时间 < self.超时时间:
            轮询次数 += 1
            try:
                data = self.shell进程.read_nonblocking(size=1024, timeout=0.2)
                if data:
                    输出缓存 += data
                    最后输出长度 = len(输出缓存)
                    无新输出计数 = 0
                    self.info(f"[轮询 {轮询次数}] 读取到 {len(data)} 字节，当前缓存总长度 {len(输出缓存)}")
                    # 可选：记录读取的原始数据片段（避免日志过大，可注释）
                    # self.info(f"[轮询 {轮询次数}] 数据片段: {data[:200]}")
                else:
                    无新输出计数 += 1
                    self.info(f"[轮询 {轮询次数}] 无新数据，无新输出计数={无新输出计数}")
            except pexpect.TIMEOUT:
                无新输出计数 += 1
                self.info(f"[轮询 {轮询次数}] pexpect 超时，无新输出计数={无新输出计数}")
            except pexpect.EOF:
                self.warning(f"[命令执行] Shell 进程意外结束 (EOF)，当前输出缓存长度: {len(输出缓存)}")
                return self.去命令回显(输出缓存, command), False, True, None

            # 检查是否出现 shell 提示符（命令正常结束）
            if self.提示符标记 in 输出缓存:
                self.info(f"[命令执行] 检测到提示符标记 '{self.提示符标记}'，命令正常结束")
                # 提取命令输出部分（不含提示符）
                清理的输出 = 输出缓存.split(self.提示符标记, 1)[0]
                清理的输出 = self.去命令回显(清理的输出, command)
                清理的输出 = self.过滤ANSI转义(清理的输出)
                # 记录完整输出到日志（不截断）
                self.info(f"[命令执行] 完整原始输出（含提示符）:\n{输出缓存}")
                self.info(f"[命令执行] 清理后输出长度: {len(清理的输出)} 字符")
                if len(清理的输出) > 0:
                    self.debug(f"[命令执行] 清理后输出内容:\n{清理的输出}")

                # 获取退出码
                退出码 = None
                try:
                    self.info("[命令执行] 正在获取命令退出码...")
                    self.shell进程.sendline('echo $?')
                    self.shell进程.expect(self.提示符标记, timeout=2)
                    raw = self.shell进程.before
                    self.info(f"[命令执行] echo $? 原始返回: {raw}")

                    # 移除 ANSI 转义序列并提取数字
                    ansi_escape = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
                    cleaned = ansi_escape.sub('', raw)
                    for line in cleaned.splitlines():
                        line = line.strip()
                        if line.isdigit():
                            退出码 = int(line)
                            self.info(f"[命令执行] 获取到退出码: {退出码}")
                            break
                    if 退出码 is None:
                        self.warning(f"[命令执行] 无法从输出中解析退出码: {cleaned}")
                except Exception as e:
                    self.warning(f"[命令执行] 获取退出码失败: {e}")

                self.info("[命令执行] 命令执行完成（正常结束）")
                # 关键：立即返回，不再继续轮询
                return 清理的输出.strip(), False, False, 退出码

            # 检查是否出现交互提示符
            最后的输出 = 输出缓存[-200:] if len(输出缓存) > 200 else 输出缓存
            if self.交互正则.search(最后的输出):
                self.info(f"[命令执行] 检测到交互提示符，匹配内容: {最后的输出}")
                self.info(f"[命令执行] 完整输出缓存（含交互提示符）:\n{输出缓存}")
                清理的输出 = self.去命令回显(输出缓存, command)
                清理的输出 = self.过滤ANSI转义(清理的输出)
                self.等待输入 = True
                self.info("[命令执行] 进入等待用户输入模式")
                return 清理的输出.strip(), True, False, None

            # 兜底：连续多次无新输出且无结束标志
            if 无新输出计数 >= 3:
                清理的输出 = self.去命令回显(输出缓存, command)
                清理的输出 = self.过滤ANSI转义(清理的输出)
                if not 清理的输出.strip():
                    self.info("[命令执行] 输出为空，继续等待")
                    continue
                self.warning(f"[命令执行] 连续 {无新输出计数} 次无新输出且无提示符，假定需要用户输入")
                self.info(f"[命令执行] 最后输出片段: {最后的输出}")
                self.等待输入 = True
                self.info("[命令执行] 进入等待用户输入模式（兜底分支）")
                return 清理的输出.strip(), True, False, None

        # 超时返回
        self.error(f"[命令执行] 命令执行超时 (>{self.超时时间}秒)，当前输出缓存长度: {len(输出缓存)}")
        self.info(f"[命令执行] 超时时的输出缓存内容:\n{输出缓存}")

        # 超时时发送 Ctrl+C 中断当前命令
        中断输出 = self.send_interrupt()
        输出缓存 += "\n[命令执行超时，已自动发送 Ctrl+C 中断]"
        if 中断输出:
            输出缓存 += "\n" + 中断输出

        return self.去命令回显(输出缓存, command), False, True, None

    def is_alive(self) -> bool:
        """检查 shell 进程是否存活"""
        alive = self.shell进程.isalive()
        self.debug(f"[会话] 检查存活状态: {'存活' if alive else '已死亡'}")
        if not alive:
            self.warning("[会话] Shell 进程已终止")
        return alive

    def close(self):
        """关闭会话，终止子进程"""
        if self.is_alive():
            self.info("[会话] 正在主动关闭 Shell 会话")
            self.shell进程.close(force=True)
            self.debug("[会话] Shell 进程已强制终止")
        else:
            self.debug("[会话] Shell 会话已经关闭，无需重复关闭")

    @property
    def waiting_for_input(self) -> bool:
        """是否正在等待用户补充输入"""
        self.debug(f"[会话] 查询等待输入标志: {self.等待输入}")
        return self.等待输入

    async def 发送命令(self, command: str) -> Tuple[str, bool, int | None]:
        """异步发送命令，返回 (输出内容, 是否仍需等待输入, 退出码)"""
        self.info(f"[会话] 异步发送命令，命令内容: {command}")
        loop = asyncio.get_running_loop()
        输出, 等待中, 错误, 退出码 = await loop.run_in_executor(
            None, self._send_command_sync, command
        )
        if 错误:
            输出 += "\n[命令执行超时或会话意外结束]"
            self.error("[会话] 命令执行返回错误状态")
        self.info(f"[会话] 命令执行结果: 等待输入={等待中}, 错误={错误}, 退出码={退出码}, 输出长度={len(输出)}")
        return 输出, 等待中, 退出码

    @staticmethod
    def 过滤ANSI转义(text: str) -> str:
        ansi_escape = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')
        return ansi_escape.sub('', text)

    # 使用统一的日志输出
    def info(self, v):
        if self.记录日志:
            logger.info(v)

    @staticmethod
    def warning(v):
        logger.warning(v)

    @staticmethod
    def error(v):
        logger.error(v)

    @staticmethod
    def debug(v):
        logger.debug(v)


class shell执行器(Star):

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.超时时间: int = config.超时时间
        self.记录日志: bool = config.记录日志
        self.最大输出长度: int = config.最大输出长度

        config.授权用户 = [i.strip() for i in config.授权用户 if i.strip()]
        self.授权用户: list[str] = config.授权用户
        self.info(f"[配置] 授权用户列表: {self.授权用户}")

        config.危险命令 = [i.strip() for i in config.危险命令 if i.strip()]
        if not config.危险命令:
            config.危险命令 = self.获取默认值('危险命令', [])
        self.危险命令: list[str] = config.危险命令
        self.info(f"[配置] 危险命令模式: {self.危险命令}")

        插件目录 = os.path.dirname(os.path.abspath(__file__))
        默认工作目录 = os.path.join(插件目录, "工作目录")
        config.工作目录 = config.工作目录.strip()
        if not config.工作目录:
            config.工作目录 = 默认工作目录
        self.工作目录: str = config.工作目录
        os.makedirs(self.工作目录, exist_ok=True)
        self.info(f"[配置] 工作目录: {self.工作目录}")

        # 保存配置
        config.save_config()
        self.debug("[配置] 配置文件已保存")

        # 用户会话管理
        self.会话管理 = {}  # 用户ID -> 会话
        logger.info("[插件] shell执行器初始化完成")
        logger.info("[插件] 最终配置详情:")
        for i, j in self.__dict__.items():
            logger.info(f"  {i}: {j}")

    def 包含危险命令(self, 命令: str) -> bool:
        """检查命令是否包含危险模式"""
        self.debug(f"[安全检查] 检查命令是否包含危险模式: {命令}")
        for pattern in self.危险命令:
            if pattern in 命令:
                self.warning(f"[安全检查] 检测到危险命令模式 '{pattern}'，命令原文: {命令}")
                return True
        self.debug("[安全检查] 未检测到危险模式")
        return False

    async def 处理会话命令(self, event: AstrMessageEvent, 用户ID: str, 用户输入: str) -> None:
        """处理用户输入（新命令或交互响应）"""
        logger.info(f"[用户 {用户ID}] 通过校验，执行命令：{用户输入}")
        self.debug(f"[用户 {用户ID}] 开始处理命令/输入，内容: {用户输入}")
        if 用户ID not in self.会话管理:
            self.info(f"[用户 {用户ID}] 不存在会话，正在创建新会话")
            会话 = 交互式Shell会话(self.工作目录, self.超时时间, self.记录日志)
            self.会话管理[用户ID] = 会话
            self.debug(f"[用户 {用户ID}] 新会话已创建并存入管理字典")
        else:
            self.info(f"[用户 {用户ID}] 复用已有会话")
        会话 = self.会话管理[用户ID]

        if not 会话.is_alive():
            self.warning(f"[用户 {用户ID}] 会话已失效，重新创建")
            会话 = 交互式Shell会话(self.工作目录, self.超时时间, self.记录日志)
            self.会话管理[用户ID] = 会话
            self.debug(f"[用户 {用户ID}] 新会话已替换失效会话")

        self.debug(f"[用户 {用户ID}] 准备发送命令到会话")
        输出, 等待中, 退出码 = await 会话.发送命令(用户输入)

        # 将完整输出记录到日志（不截断）
        logger.info(f"[用户 {用户ID}] 命令执行完成，原始输出：\n{输出}")
        if 等待中:
            logger.info(f"等待下一个命令")
        else:
            logger.info(f"退出码：{退出码}")

        输出 = 输出.strip()
        if not 输出:
            输出 = "（无输出）"
            self.info(f"[用户 {用户ID}] 命令无输出")

        if len(输出) > self.最大输出长度:
            self.info(f"[用户 {用户ID}] 输出过长 ({len(输出)} 字符)，截断至 {self.最大输出长度} 字符用于回复")
            输出 = 输出[:self.最大输出长度] + "\n... (输出过长已截断)"

        if not 等待中 and not 会话.is_alive():
            self.info(f"[用户 {用户ID}] 会话已结束，从管理器中移除")
            del self.会话管理[用户ID]
            self.debug(f"[用户 {用户ID}] 会话已从管理字典删除")

        if 等待中:
            self.info(f"[用户 {用户ID}] 命令触发交互模式，等待用户进一步输入")
            回复文本 = f"🔄 需要继续输入：\n```\n{输出}\n```\n请发送下一步输入"
            self.debug(f"[用户 {用户ID}] 回复内容（交互等待）: {回复文本}")
            await self.发送回复文本(event, 回复文本)
        else:
            self.info(f"[用户 {用户ID}] 命令执行完成，输出长度 {len(输出)}")
            回复文本 = f"✅ 执行完成：\n```\n{输出}\n```"
            # 附加返回码
            if 退出码 is not None:
                回复文本 += f"\n退出码: {退出码}"
                self.info(f"[用户 {用户ID}] 附加退出码: {退出码}")
            self.debug(f"[用户 {用户ID}] 回复内容（完成）: {回复文本}")
            await self.发送回复文本(event, 回复文本)

    @filter.command(command_name="shell", alias={"sh"})
    async def 执行shell命令(self, event: AstrMessageEvent):
        """执行 shell 命令或响应交互式输入"""
        用户ID = event.get_sender_id()
        self.info("[Shell执行器]=================================================[开始]")
        self.info(f"[请求] 收到来自用户 {用户ID} 的 shell 命令请求，完整消息原文: {event.message_str}")

        # 权限检查
        if 用户ID not in self.授权用户:
            logger.warning(f"[权限] 用户 {用户ID} 无权使用 shell 执行器，拒绝执行")
            await self.发送回复文本(event, "❌ 你没有权限")
            return
        self.info(f"[权限] 用户 {用户ID} 通过权限检查")

        消息文本 = event.message_str.strip()
        分割 = 消息文本.split(" ", 1)
        用户输入内容 = 分割[1].strip() if len(分割) > 1 else ""
        self.info(f"[请求] 提取的用户输入内容: {用户输入内容}")

        # 特殊命令：重置会话
        if 用户输入内容 == "reset":
            self.info(f"[用户 {用户ID}] 请求重置会话")
            if 用户ID in self.会话管理:
                self.debug(f"[用户 {用户ID}] 找到现有会话，准备关闭")
                self.会话管理[用户ID].close()
                del self.会话管理[用户ID]
                self.debug(f"[用户 {用户ID}] 会话已关闭并移除")
            else:
                self.debug(f"[用户 {用户ID}] 没有活动会话，无需重置")
            await self.发送回复文本(event, "♻️ 会话已重置")
            return

        # 特殊命令：中断当前命令 (stop)
        if 用户输入内容 == "stop":
            logger.info(f"[用户 {用户ID}] 请求中断当前命令")
            会话 = self.会话管理.get(用户ID)
            if not 会话:
                await self.发送回复文本(event, "ℹ️ 当前没有活动的 shell 会话")
                return
            if not 会话.waiting_for_input:
                # 如果没有等待输入，说明可能正在执行命令
                中断输出 = 会话.send_interrupt()
                if 中断输出:
                    回复文本 = f"🛑 已发送中断信号\n```\n{中断输出}\n```"
                else:
                    回复文本 = "🛑 已发送中断信号（无额外输出）"
                await self.发送回复文本(event, 回复文本)
            else:
                # 如果正在等待输入，直接取消等待状态并重置
                会话.等待输入 = False
                await self.发送回复文本(event, "🛑 已取消等待输入状态")
            return

        # 检查是否有一个正在等待输入的会话
        会话 = self.会话管理.get(用户ID)
        if 会话 and 会话.waiting_for_input:
            self.info(f"[用户 {用户ID}] 存在等待输入的会话，将输入作为交互响应处理")
            await self.处理会话命令(event, 用户ID, 用户输入内容)
            return

        # 如果没有等待输入的会话，则当作新命令处理
        if not 用户输入内容:
            self.info(f"[用户 {用户ID}] 未提供命令内容")
            await self.发送回复文本(event, "请提供要执行的命令。使用方法: /shell <命令>")
            return

        # 危险命令拦截
        if self.包含危险命令(用户输入内容):
            self.warning(f"[用户 {用户ID}] 命令包含危险词，已拦截: {用户输入内容}")
            await self.发送回复文本(event, f"❌ 命令包含危险词，已被拦截。")
            return

        # 执行命令（自动创建或复用会话）
        await self.处理会话命令(event, 用户ID, 用户输入内容)
        self.info("[Shell执行器]=================================================[结束]")

    async def 发送回复文本(self, event: AstrMessageEvent, 文本: str) -> None:
        """发送回复消息，并记录回复内容到日志"""
        self.debug(f"[回复] 准备发送回复，内容: {文本}")
        await event.send(event.chain_result([Reply(id=event.message_obj.message_id), Plain(文本)]))
        self.debug("[回复] 消息已发送")

    @filter.command(command_name="ctrl", alias={"sh^", "^sh", "sh+", "+sh", "c"})
    async def 发送控制键(self, event: AstrMessageEvent):
        """向当前 shell 会话发送 Ctrl 组合键"""
        用户ID = event.get_sender_id()
        self.info(f"[Ctrl] 用户 {用户ID} 请求发送控制键，原始消息: {event.message_str}")

        # 权限检查
        if 用户ID not in self.授权用户:
            await self.发送回复文本(event, "❌ 你没有权限")
            return

        # 解析参数
        消息文本 = event.message_str.strip()
        分割 = 消息文本.split(" ", 1)
        参数 = 分割[1].strip() if len(分割) > 1 else ""

        if not 参数:
            await self.发送回复文本(event, "请指定要发送的 Ctrl 组合键，例如：/ctrl c  或  /ctrl d")
            return

        # 提取字母（仅取第一个字符，并转为小写）
        字母 = 参数[0].lower()
        if not 字母.isalpha():
            await self.发送回复文本(event, f"无效的控制键 '{参数[0]}'，请输入单个字母")
            return

        # 获取用户会话
        会话 = self.会话管理.get(用户ID)
        if not 会话 or not 会话.is_alive():
            # 没有活动会话，创建新会话以便发送控制键（例如 ^D 退出后可能需要新会话）
            会话 = 交互式Shell会话(self.工作目录, self.超时时间, self.记录日志)
            self.会话管理[用户ID] = 会话
            self.info(f"[Ctrl] 用户 {用户ID} 没有活动会话，已创建新会话")

        # 发送控制键
        try:
            会话.shell进程.sendcontrol(字母)
            logger.info(f"[Ctrl] 已向用户 {用户ID} 的会话发送 Ctrl+{字母.upper()}")
        except Exception as e:
            await self.发送回复文本(event, f"❌ 发送控制键失败：{e}")
            return

        # 读取立即返回的输出（可选，让用户知道效果）
        time.sleep(0.1)  # 短暂等待
        输出 = ""
        try:
            while True:
                data = 会话.shell进程.read_nonblocking(size=1024, timeout=0.1)
                if data:
                    输出 += data
                else:
                    break
        except pexpect.TIMEOUT:
            pass
        except pexpect.EOF:
            self.warning(f"[Ctrl] 用户 {用户ID} 的 shell 进程在发送控制键后 EOF")

        输出 = 会话.过滤ANSI转义(输出).strip()
        if 输出:
            if len(输出) > self.最大输出长度:
                输出 = 输出[:self.最大输出长度] + "\n... (输出过长已截断)"
            回复文本 = f"⌨️ 已发送 Ctrl+{字母.upper()}\n```\n{输出}\n```"
        else:
            回复文本 = f"⌨️ 已发送 Ctrl+{字母.upper()}"

        await self.发送回复文本(event, 回复文本)

    def 获取默认值(self, 键, 默认=None) -> Any:
        """获取顶层配置的默认值，不适用于二层"""
        val = self.config.schema[键].get('default', 默认)
        self.info(f"[配置] 获取默认值: {键} = {val}")
        return val

    # 使用统一的日志输出
    def info(self, v):
        if self.记录日志:
            logger.info(v)

    @staticmethod
    def warning(v):
        logger.warning(v)

    @staticmethod
    def error(v):
        logger.error(v)

    @staticmethod
    def debug(v):
        logger.debug(v)

    async def terminate(self):
        """当插件被禁用、重载插件时会调用这个方法"""
        for i in self.会话管理:
            try:
                self.会话管理[i].close()
            except Exception as e:
                logger.warning(e, exc_info=True)