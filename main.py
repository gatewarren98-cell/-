import os
import json
import aiohttp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Image

# ！！请务必在此处填入你申请的 ALS API Key ！！
ALS_API_KEY = "b7bc7443be72109d3c31e3fc85d3183f"

# ==========================================
# 本地数据存储路径初始化
# ==========================================
PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
BIND_FILE = os.path.join(PLUGIN_DIR, "QQ_EA_ID.json")       # 存储 QQ 与 EA ID 的绑定关系
RANK_FILE = os.path.join(PLUGIN_DIR, "Rank_Data.json")      # 存储历史段位分数，用于计算 RP 增减

# 确保数据文件存在
for file_path in [BIND_FILE, RANK_FILE]:
    if not os.path.exists(file_path):
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({}, f)

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


@register("apex_tool_pro", "开发者", "复刻 AreCie/Apex_Tool 的硬核查询插件", "2.0.0")
class ApexToolPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    # ==========================
    # 功能一：账号绑定系统
    # ==========================
    @filter.command("绑定apex")
    async def bind_apex(self, event: AstrMessageEvent, ea_id: str = ""):
        if not ea_id:
            yield event.plain_result("❌ 请输入需要绑定的 EA ID，例如：/绑定apex ItzTimmy")
            return
            
        user_id = str(event.get_sender_id())
        bindings = load_json(BIND_FILE)
        bindings[user_id] = ea_id
        save_json(BIND_FILE, bindings)
        yield event.plain_result(f"✅ 绑定成功！您的 QQ 现已绑定至 EA ID: {ea_id}")

    @filter.command("解绑apex")
    async def unbind_apex(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        bindings = load_json(BIND_FILE)
        if user_id in bindings:
            del bindings[user_id]
            save_json(BIND_FILE, bindings)
            yield event.plain_result("✅ 已解除您的 EA ID 绑定。")
        else:
            yield event.plain_result("⚠️ 您当前没有绑定任何 EA ID。")

    # ==========================
    # 功能二：玩家数据查询 (带 RP 变动和状态监测)
    # ==========================
    @filter.command("查apex")
    async def query_apex(self, event: AstrMessageEvent, player_name: str = ""):
        user_id = str(event.get_sender_id())
        
        # 逻辑：如果不填 ID，则读取本地绑定数据
        if not player_name:
            bindings = load_json(BIND_FILE)
            if user_id in bindings:
                player_name = bindings[user_id]
            else:
                yield event.plain_result("❌ 请提供玩家ID，或先使用 /绑定apex [ID] 绑定账号。")
                return

        yield event.plain_result(f"⏳ 正在查询 {player_name} 的数据...")
        
        url = "https://api.mozambiquehe.re/bridge"
        params = {"auth": ALS_API_KEY, "player": player_name, "platform": "PC"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, ssl=False) as response:
                    data = await response.json()
                    
                    # 精准拦截各种 API 报错（还原 AreCie 逻辑）
                    if "Error" in data:
                        err_msg = data['Error'].lower()
                        if "not found" in err_msg:
                            yield event.plain_result(f"❌ 烂橘子 ID 错误：找不到玩家 {player_name}，请检查是否输入错误或未在 PC 端游玩。")
                        else:
                            yield event.plain_result(f"❌ 查询失败：{data['Error']}")
                        return

                    global_data = data.get("global", {})
                    rank_data = global_data.get("rank", {})
                    realtime_data = data.get("realtime", {})
                    
                    level = global_data.get("level", "未知")
                    rank_name = rank_data.get("rankName", "未知")
                    rank_div = rank_data.get("rankDiv", "")
                    rank_score = rank_data.get("rankScore", 0)
                    
                    # 账号封禁监测
                    is_banned = global_data.get("bans", {}).get("isActive", False)
                    ban_text = "🚫 已封禁" if is_banned else "🟢 正常"
                    
                    # 实时在线状态监测
                    is_online = realtime_data.get("isOnline", 0)
                    is_in_game = realtime_data.get("isInGame", 0)
                    if is_online:
                        state_text = "⚔️ 游戏中" if is_in_game else "🍵 在线 (大厅挂机)"
                    else:
                        state_text = "⚪ 离线"

                    # 核心机制：读取并计算 RP 分数变动
                    rank_history = load_json(RANK_FILE)
                    rp_diff = 0
                    if player_name in rank_history:
                        rp_diff = rank_score - rank_history[player_name]
                        
                    # 覆写最新的分数到本地文件
                    rank_history[player_name] = rank_score
                    save_json(RANK_FILE, rank_history)

                    # 渲染变动文案
                    if rp_diff > 0:
                        rp_change_text = f"上分 📈 +{rp_diff}"
                    elif rp_diff < 0:
                        rp_change_text = f"掉分 📉 {rp_diff}"
                    else:
                        rp_change_text = "无变动 ➖"

            msg = (
                f"🎮 玩家: {player_name}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🔰 等级: Lv.{level}\n"
                f"🏆 排位: {rank_name} {rank_div} - {rank_score} RP\n"
                f"📊 变动: {rp_change_text}\n"
                f"🎫 状态: {state_text}\n"
                f"🛡️ 封禁: {ban_text}\n"
                f"━━━━━━━━━━━━━━━"
            )
            yield event.plain_result(msg)
            
        except Exception as e:
            logger.error(f"Apex查询异常: {e}")
            yield event.plain_result("❌ 网络请求超时或异常，请稍后再试。")

    # ==========================
    # 功能三：地图轮换 (包含混合模式)
    # ==========================
    @filter.command("apex地图")
    async def query_apex_map(self, event: AstrMessageEvent):
        url = "https://api.mozambiquehe.re/maprotation"
        params = {"auth": ALS_API_KEY, "version": "2"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, ssl=False) as response:
                    data = await response.json()
                    if "Error" in data:
                        yield event.plain_result(f"❌ 查询失败：{data['Error']}")
                        return
                    
                    pubs = data.get("battle_royale", {})
                    ranked = data.get("ranked", {})
                    ltm = data.get("ltm", {}) # LTM = 混合模式/街机

                    pubs_curr = pubs.get("current", {})
                    ranked_curr = ranked.get("current", {})
                    ltm_curr = ltm.get("current", {})

            msg = (
                f"🗺️ 𝗔𝗣𝗘𝗫 地图轮换\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🗡️ 【匹配】 {pubs_curr.get('map', '未知')}\n"
                f"⏳ 剩余: {pubs_curr.get('remainingTimer', '')}\n"
                f"➤ 下张: {pubs.get('next', {}).get('map', '未知')}\n\n"
                
                f"🏆 【排位】 {ranked_curr.get('map', '未知')}\n"
                f"⏳ 剩余: {ranked_curr.get('remainingTimer', '')}\n"
                f"➤ 下张: {ranked.get('next', {}).get('map', '未知')}\n\n"
                
                f"🕹️ 【混合】 {ltm_curr.get('map', '未知')}\n"
                f"⏳ 剩余: {ltm_curr.get('remainingTimer', '')}\n"
                f"➤ 模式: {ltm_curr.get('eventName', '未知')}\n"
                f"━━━━━━━━━━━━━━━"
            )

            # 依旧附加上官方的当前排位大图
            res = event.make_result().message(msg)
            if ranked_curr.get("asset"):
                res.chain.append(Image.fromURL(ranked_curr.get("asset")))
            yield res
            
        except Exception as e:
            logger.error(f"地图查询异常: {e}")
            yield event.plain_result("❌ 地图获取异常，请稍后再试。")

    # ==========================
    # 功能四：PC端猎杀门槛
    # ==========================
    @filter.command("apex猎杀")
    async def query_apex_predator(self, event: AstrMessageEvent):
        url = "https://api.mozambiquehe.re/predator"
        params = {"auth": ALS_API_KEY}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, ssl=False) as response:
                    # 关键修复：添加 content_type=None 强制解析
                    data = await response.json(content_type=None)
                    
                    rp_data = data.get("RP", {})
                    pc = rp_data.get("PC", {})
                    ps4 = rp_data.get("PS4", {})
                    x1 = rp_data.get("X1", {})
                    sw = rp_data.get("SWITCH", {})
            
            msg = (
                f"👹 𝗔𝗣𝗘𝗫 全平台猎杀底分\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💻 PC端: {pc.get('val', '未知')} RP ({pc.get('totalMastersAndPreds', 0)}大师)\n"
                f"🎮 PS端: {ps4.get('val', '未知')} RP ({ps4.get('totalMastersAndPreds', 0)}大师)\n"
                f"🎮 Xbox: {x1.get('val', '未知')} RP ({x1.get('totalMastersAndPreds', 0)}大师)\n"
                f"🍄 SW端: {sw.get('val', '未知')} RP ({sw.get('totalMastersAndPreds', 0)}大师)\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💡 包含全服前750名及大师段位统计"
            )
            yield event.plain_result(msg)
            
        except Exception as e:
            logger.error(f"猎杀查询异常: {e}")
            yield event.plain_result("❌ 猎杀数据解析失败，请稍后再试。")
# ==========================
    # 功能五：EA 服务器状态 (带多地区检测)
    # ==========================
    @filter.command("apex服务器")
    async def query_apex_servers(self, event: AstrMessageEvent):
        url = "https://api.mozambiquehe.re/servers"
        params = {"auth": ALS_API_KEY}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, ssl=False) as response:
                    # 同样强制解析 JSON
                    data = await response.json(content_type=None)

            # 辅助逻辑：优先检查亚洲区，如果亚洲区没数据则检查全局
            def check_service(service_name):
                service = data.get(service_name, {})
                asia = service.get("Asia", {})
                status = asia.get("Status", "UNKNOWN")
                
                if status == "UP":
                    return "🟢 正常"
                elif status == "SLOW":
                    return "🟡 缓慢"
                elif status == "DOWN":
                    return "🔴 离线"
                else:
                    # 如果 Asia 没数据，遍历所有地区看看有没有 DOWN 的
                    for reg, info in service.items():
                        if info.get("Status") != "UP":
                            return "🔴 异常"
                    return "🟢 正常"

            # 提取核心服务
            origin_login = check_service("Origin_login")
            ea_accounts = check_service("EA_accounts")
            novafusion = check_service("EA_novafusion")
            crossplay = check_service("ApexOauth_Crossplay")
            
            # 提取第三方平台状态
            other = data.get("otherPlatforms", {})
            psn = "🟢" if other.get("Playstation-Network", {}).get("Status") == "UP" else "🔴"
            xbox = "🟢" if other.get("Xbox-Live", {}).get("Status") == "UP" else "🔴"

            msg = (
                f"📡 𝗘𝗔 官方服务器状态 (亚洲区)\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🔑 账户登录: {origin_login}\n"
                f"👤 账号关联: {ea_accounts}\n"
                f"⚔️ 核心匹配: {novafusion}\n"
                f"🔄 跨平台连接: {crossplay}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🎮 平台网络: PSN {psn} | Xbox {xbox}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"💡 若核心匹配显示异常，游戏中可能会出现无法连接服务器或无限转圈。"
            )
            yield event.plain_result(msg)
            
        except Exception as e:
            logger.error(f"服务器查询异常: {e}")
            yield event.plain_result("❌ 无法获取服务器实时状态，请稍后再试。")
