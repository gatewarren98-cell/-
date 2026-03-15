import os
import uuid
import tempfile
import asyncio
import httpx

from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
from astrbot.api.event.filter import event_message_type, EventMessageType
from astrbot.core.message.message_event_result import MessageChain

@register("hachimi_voice", "YourName", "哈基米语音降音量插件", "1.0.0")
class HachimiVoice(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 依赖检查：启动时可以顺便检查一下系统有没有装 ffmpeg
        asyncio.create_task(self._check_ffmpeg())

    async def _check_ffmpeg(self):
        try:
            process = await asyncio.create_subprocess_shell(
                "ffmpeg -version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            if process.returncode != 0:
                logger.warning("[哈基米] 系统中似乎未正确安装或配置 FFmpeg，插件可能无法工作！")
        except Exception:
            logger.warning("[哈基米] 无法检测到 FFmpeg，请确保系统已安装 FFmpeg 且已加入环境变量。")

    # 限定只在群聊消息中触发 (对应 JS 的 if (event.message_type !== 'group') return)
    @event_message_type(EventMessageType.GROUP_MESSAGE)
    async def on_hachimi_message(self, event: AstrMessageEvent):
        # 获取纯文本消息内容
        msg = event.message_obj.message_str.strip()
        
        # 严格匹配关键词
        if msg != "哈基米":
            return

        logger.info("[哈基米] 触发关键词，开始处理语音...")

        try:
            # 1. 获取音频 URL
            async with httpx.AsyncClient(timeout=10.0) as client:
                api_res = await client.get('http://api.ocoa.cn/api/hjm.php')
                api_res.raise_for_status()
                api_data = api_res.json()
                
                audio_url = api_data.get("url")
                if not audio_url:
                    logger.error("[哈基米] 接口未返回有效的 URL")
                    return

                # 2. 下载原始音频到内存
                audio_res = await client.get(audio_url)
                audio_res.raise_for_status()
                audio_bytes = audio_res.content
        except Exception as e:
            logger.error(f"[哈基米] 网络请求或下载失败: {e}")
            return

        # 3. 生成系统临时文件路径
        temp_dir = tempfile.gettempdir()
        temp_id = uuid.uuid4().hex[:8]
        input_path = os.path.join(temp_dir, f"hjm_in_{temp_id}.mp3")
        output_path = os.path.join(temp_dir, f"hjm_out_{temp_id}.mp3")

        try:
            # 将下载的音频写入临时文件
            with open(input_path, "wb") as f:
                f.write(audio_bytes)

            # 4. 使用 FFmpeg 修改音量 (异步非阻塞执行)
            # volume=0.2 表示放大到 20%
            volume_level = "0.2"
            cmd = f'ffmpeg -y -i "{input_path}" -filter:a "volume={volume_level}" "{output_path}"'
            
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"[哈基米] FFmpeg 处理失败: {stderr.decode('utf-8', errors='ignore')}")
                return

            # 5. 发送处理后的本地音频
            # AstrBot 原生支持直接通过 .record() 发送本地音频路径
            await event.send(MessageChain().record(output_path))
            logger.info("[哈基米] 语音处理并发送成功！")

        except Exception as e:
            logger.error(f"[哈基米] 音频处理发送过程发生异常: {e}")
        finally:
            # 6. 安全清理临时文件
            if os.path.exists(input_path):
                try:
                    os.remove(input_path)
                except OSError:
                    pass
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except OSError:
                    pass
