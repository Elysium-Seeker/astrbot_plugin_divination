import asyncio
import json
import logging
import os
import random
import re
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import PIL.Image
import PIL.ImageDraw
import PIL.ImageFont
from astrbot.api.all import *
import markdown
from playwright.async_api import async_playwright
from astrbot.api.event import AstrMessageEvent, filter

logger = logging.getLogger(__name__)

class Tarot:
    def __init__(self, context: Context, config: AstrBotConfig):
        self.context = context
        self.tarot_json: Path = Path(__file__).parent / "tarot.json"
        resource_path_str: str = config.get("resource_path", "./resources")
        self.resource_path: Path = Path(__file__).parent / resource_path_str
        self.is_chain_reply: bool = config.get("chain_reply", True)
        self.include_ai_in_chain: bool = config.get("include_ai_in_chain", True)
        self.pending_expire_seconds: int = int(config.get("pending_expire_seconds", 600))
        self.enable_record: bool = config.get("enable_record", True)
        self.full_draw_pool: bool = config.get("full_draw_pool", True)
        self.draw_pool_factor: int = max(0, int(config.get("draw_pool_factor", 0)))
        raw_force_theme = config.get("force_theme", "BilibiliTarot")
        self.force_theme: str = str(raw_force_theme).strip() if raw_force_theme is not None else ""
        self.enable_markdown_card: bool = config.get("enable_markdown_card", True)
        raw_card_font_path = config.get("markdown_card_font_path", "")
        self.markdown_card_font_path: str = str(raw_card_font_path).strip() if raw_card_font_path is not None else ""
        self.pending_sessions: Dict[str, Dict[str, Any]] = {}
        self.record_lock = asyncio.Lock()
        self.data_dir: Path = self._resolve_data_dir(context)
        self.records_file: Path = self.data_dir / "divination_records.jsonl"

        os.makedirs(self.resource_path, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        if not self.tarot_json.exists():
            logger.error("tarot.json 文件缺失，请确保资源完整！")
            raise Exception("tarot.json 文件缺失，请确保资源完整！")
        logger.info(
            "Tarot 插件初始化完成，资源路径: %s, AI 解析加入转发: %s, 记录功能: %s, 全牌池: %s, 抽牌池倍率: %s, 强制主题: %s, Markdown 卡片: %s, 卡片字体: %s",
            self.resource_path,
            self.include_ai_in_chain,
            self.enable_record,
            self.full_draw_pool,
            self.draw_pool_factor,
            self.force_theme or "<随机>",
            self.enable_markdown_card,
            self.markdown_card_font_path or "<自动探测>",
        )

    def _resolve_data_dir(self, context: Context) -> Path:
        data_dir_getter = getattr(context, "get_data_dir", None)
        if callable(data_dir_getter):
            try:
                data_dir = data_dir_getter()
                if data_dir:
                    return Path(data_dir)
            except Exception as e:
                logger.warning("获取 AstrBot 数据目录失败，回退到插件 data 目录: %s", str(e))
        return Path(__file__).parent / "data"

    def _safe_event_call(self, event: AstrMessageEvent, method_name: str) -> Optional[Any]:
        method = getattr(event, method_name, None)
        if callable(method):
            try:
                return method()
            except Exception:
                return None
        return None

    def _build_session_key(self, event: AstrMessageEvent) -> str:
        group_id = self._safe_event_call(event, "get_group_id")
        user_id = self._safe_event_call(event, "get_sender_id")
        if user_id is None:
            user_id = self._safe_event_call(event, "get_user_id")
        if user_id is None:
            user_id = self._safe_event_call(event, "get_session_id")
        if user_id is None:
            user_id = "unknown-user"
        if group_id is not None:
            return f"group:{group_id}:user:{user_id}"
        return f"private:user:{user_id}"

    def has_pending_session(self, event: AstrMessageEvent) -> bool:
        self._cleanup_pending_sessions()
        session_key = self._build_session_key(event)
        session = self.pending_sessions.get(session_key)
        if not session:
            return False
        if time.time() - session.get("created_at", 0) > self.pending_expire_seconds:
            self.pending_sessions.pop(session_key, None)
            return False
        return True

    def _cleanup_pending_sessions(self):
        now = time.time()
        expired_keys = [
            key
            for key, session in self.pending_sessions.items()
            if now - session.get("created_at", now) > self.pending_expire_seconds
        ]
        for key in expired_keys:
            self.pending_sessions.pop(key, None)

    def _normalize_question(self, user_input: str) -> str:
        question = re.sub(r"\s+", " ", user_input or "").strip()
        return question or "我当前最需要关注什么？"

    def _load_tarot_content(self) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        with open(self.tarot_json, "r", encoding="utf-8") as f:
            content = json.load(f)
        all_cards = content.get("cards") or {}
        all_formations = content.get("formations") or {}
        if not all_cards:
            raise Exception("tarot.json 中缺少 cards 定义")
        if not all_formations:
            raise Exception("tarot.json 中缺少 formations 定义")
        return all_cards, all_formations

    def pick_theme(self) -> str:
        sub_themes_dir: List[str] = [f.name for f in self.resource_path.iterdir() if f.is_dir()]
        if not sub_themes_dir:
            logger.error("本地塔罗牌主题为空，请检查资源目录！")
            raise Exception("本地塔罗牌主题为空，请检查资源目录！")

        if self.force_theme:
            matched_theme = {name.lower(): name for name in sub_themes_dir}.get(self.force_theme.lower())
            if matched_theme:
                return matched_theme
            logger.warning(
                "force_theme=%s 不存在，可用主题: %s。将回退为随机主题。",
                self.force_theme,
                ", ".join(sub_themes_dir),
            )

        return random.choice(sub_themes_dir)

    def pick_sub_types(self, theme: str) -> List[str]:
        all_sub_types: List[str] = ["MajorArcana", "Cups", "Pentacles", "Swords", "Wands"]
        sub_types: List[str] = [
            f.name for f in (self.resource_path / theme).iterdir()
            if f.is_dir() and f.name in all_sub_types
        ]
        return sub_types or all_sub_types

    def _all_candidate_cards(self, all_cards: Dict[str, Any], theme: str) -> List[Dict[str, Any]]:
        sub_types = self.pick_sub_types(theme)
        cards = [card for card in all_cards.values() if card.get("type") in sub_types]
        if not cards:
            raise Exception(f"主题 {theme} 下没有可抽取的牌")
        return cards

    def _build_draw_pool(self, all_cards: Dict[str, Any], theme: str, cards_num: int) -> List[Dict[str, Any]]:
        candidates = self._all_candidate_cards(all_cards, theme)
        if len(candidates) < cards_num:
            raise Exception(f"主题 {theme} 的牌数量不足，需要 {cards_num} 张")

        # 默认开启全牌池，兼容旧配置里保留 draw_pool_factor=3 的情况。
        if self.full_draw_pool or self.draw_pool_factor <= 0:
            pool_size = len(candidates)
        else:
            pool_size = min(len(candidates), max(cards_num + 2, cards_num * self.draw_pool_factor))
        return random.sample(candidates, pool_size)

    def _normalize_representations(self, representations: List[str], cards_num: int) -> List[str]:
        result = list(representations[:cards_num])
        while len(result) < cards_num:
            result.append(f"位置{len(result) + 1}")
        return result

    def _format_pool_numbers(self, pool_size: int) -> str:
        numbers = [str(i) for i in range(1, pool_size + 1)]
        return "\n".join(" ".join(numbers[i:i + 10]) for i in range(0, len(numbers), 10))

    @staticmethod
    def _normalize_markdown_text(text: str) -> str:
        normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
        normalized = "".join(ch for ch in normalized if ch == "\n" or ch == "\t" or ord(ch) >= 32)
        return normalized.strip()

    def _build_interpretation_markdown(
        self,
        question: str,
        formation_name: str,
        record_cards: List[Dict[str, Any]],
        interpretation: str,
    ) -> str:
        lines = [
            "# 塔罗占卜分析卡",
            "## 问题",
            f"- {question}",
            "## 牌阵",
            f"- {formation_name}",
            "## 牌面概览",
        ]
        for card in record_cards:
            lines.append(
                f"- {card.get('position', '位置')}：{card.get('name', '未知牌')}{card.get('orientation', '')} · {card.get('meaning', '')}"
            )

        lines.append("---")
        lines.append("## 深度解读")
        normalized_interpretation = self._normalize_markdown_text(interpretation)
        content_lines = [line.strip() for line in normalized_interpretation.splitlines() if line.strip()]
        if not content_lines:
            lines.append("- 暂无解读。")
        else:
            lines.extend(content_lines)
        return "\n".join(lines)

    async def _render_markdown_card(self, markdown_text: str) -> Optional[str]:
        if not self.enable_markdown_card:
            return None

        markdown_text = self._normalize_markdown_text(markdown_text)
        if not markdown_text:
            return None
        
        try:
            html_content = markdown.markdown(markdown_text)
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset='utf-8'>
                <style>
                    @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;700&display=swap');
                    body {{
                        font-family: "Noto Serif SC", "Microsoft YaHei", serif;
                        background-color: #0d0914;
                        color: #e8dcc4;
                        padding: 40px;
                        margin: 0;
                        width: 800px;
                    }}
                    .card {{
                        background: radial-gradient(circle at top center, #261a35 0%, #120c1c 100%);
                        border: 2px solid #8c734b;
                        border-radius: 12px;
                        padding: 50px 40px;
                        box-shadow: 0 0 40px rgba(0,0,0,0.8), inset 0 0 20px rgba(140, 115, 75, 0.2);
                        position: relative;
                    }}
                    .card::before {{
                        content: '';
                        position: absolute;
                        top: 10px; bottom: 10px; left: 10px; right: 10px;
                        border: 1px solid rgba(212, 175, 55, 0.3);
                        border-radius: 8px;
                        pointer-events: none;
                    }}
                    h1 {{
                        text-align: center;
                        color: #d4af37;
                        font-size: 32px;
                        font-weight: 700;
                        border-bottom: 1px solid rgba(212, 175, 55, 0.3);
                        padding-bottom: 20px;
                        margin-top: 0;
                        margin-bottom: 30px;
                        letter-spacing: 4px;
                        text-shadow: 0 2px 4px rgba(0,0,0,0.5);
                    }}
                    h2 {{
                        color: #c9a45c;
                        font-size: 22px;
                        border-bottom: 1px dashed rgba(201, 164, 92, 0.3);
                        padding-bottom: 8px;
                        margin-top: 30px;
                        display: inline-block;
                        letter-spacing: 2px;
                    }}
                    h3 {{
                        color: #b89c63;
                        font-size: 18px;
                        margin-top: 25px;
                    }}
                    ul {{
                        list-style-type: none;
                        padding: 0;
                    }}
                    li {{
                        margin-bottom: 12px;
                        line-height: 1.8;
                        color: #d8caba;
                    }}
                    li::before {{
                        content: '✦ ';
                        color: #d4af37;
                        margin-right: 5px;
                    }}
                    strong {{
                        color: #f7e0a3;
                        font-weight: 700;
                    }}
                    hr {{
                        border: none;
                        border-top: 1px solid rgba(212, 175, 55, 0.2);
                        margin: 40px 0;
                    }}
                    p {{
                        line-height: 1.8;
                        margin-bottom: 15px;
                        text-align: justify;
                    }}
                </style>
            </head>
            <body id="body">
                <div class="card" id="card">
                    {html_content}
                </div>
            </body>
            </html>
            """
            
            card_dir = self.data_dir / "analysis_cards"
            os.makedirs(card_dir, exist_ok=True)
            card_path = card_dir / f"reading_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"

            launch_kwargs: Dict[str, Any] = {"headless": True}
            if os.name != "nt":
                launch_kwargs["args"] = ["--no-sandbox", "--disable-setuid-sandbox"]

            async with async_playwright() as p:
                browser = await p.chromium.launch(**launch_kwargs)
                page = await browser.new_page()
                await page.set_content(html, wait_until='networkidle')
                await page.evaluate('document.fonts.ready')
                
                card_element = await page.query_selector('.card')
                if card_element:
                    await card_element.screenshot(path=str(card_path))
                else:
                    await page.screenshot(path=str(card_path), full_page=True)
                await browser.close()

            return str(card_path.resolve())
        except Exception as e:
            error_text = str(e)
            if "Executable doesn't exist" in error_text or "chromium_headless_shell" in error_text:
                logger.warning(
                    "Markdown Playwright 渲染降级：检测到未安装浏览器内核，已回退纯文本。请在部署环境执行 'python -m playwright install chromium'。错误: %s",
                    error_text,
                )
                return None
            logger.error("Markdown Playwright 渲染失败，已回退纯文本: %s", error_text)
            return None

    async def _append_record(self, record: Dict[str, Any]):
        if not self.enable_record:
            return
        async with self.record_lock:
            with open(self.records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _parse_draw_numbers(self, text: str) -> List[int]:
        if not text:
            return []
        return [int(num) for num in re.findall(r"\d+", text)]

    def _build_preparation_message(self, question: str) -> str:
        return (
            f"已收到你的问题：{question}\n"
            "请先让自己平静下来，深呼吸三次，专注在这个问题上。\n"
            "正在净化牌组并洗牌中..."
        )

    def _build_draw_prompt(
        self,
        formation_name: str,
        theme_name: str,
        cards_num: int,
        pool_size: int,
        representations: List[str],
        is_cut: bool,
        is_single: bool,
    ) -> str:
        mode_text = "单张抽牌" if is_single else "多张牌阵"
        rep_text = "、".join(representations)
        cut_text = "本次包含切牌位。" if is_cut else "本次不包含切牌位。"
        return (
            f"牌阵已确定：{formation_name}（{mode_text}，需抽 {cards_num} 张）\n"
            f"当前牌组主题：{theme_name}\n"
            f"位置含义：{rep_text}\n"
            f"{cut_text}\n"
            "请从下方编号中选择你要抽取的牌。\n"
            "注意：编号从 1 开始，不存在 0 号牌。\n"
            "输入方式：\n"
            "1) 直接回复编号（推荐）\n"
            "2) 抽牌 编号1 编号2 ...\n"
            "3) /tarot 编号1 编号2 ...（分流兜底）\n"
            f"可选编号 1-{pool_size}：\n"
            f"{self._format_pool_numbers(pool_size)}"
        )

    def _random_cards(self, all_cards: Dict, theme: str, num: int = 1) -> List[Dict]:
        sub_types: List[str] = self.pick_sub_types(theme)
        if not sub_types:
            logger.error(f"主题 {theme} 下无可用子类型！")
            raise Exception(f"主题 {theme} 下无可用子类型！")
        subset: Dict = {k: v for k, v in all_cards.items() if v.get("type") in sub_types}
        if len(subset) < num:
            logger.error(f"主题 {theme} 的牌数量不足，需要 {num} 张，实际 {len(subset)} 张！")
            raise Exception(f"主题 {theme} 的牌数量不足！")
        cards_index: List[str] = random.sample(list(subset), num)
        return [v for k, v in subset.items() if k in cards_index]

    async def _get_text_and_image(self, theme: str, card_info: Dict) -> Tuple[bool, str, str, bool]:
        try:
            _type: str = card_info.get("type")
            _name: str = card_info.get("pic")
            img_dir: Path = self.resource_path / theme / _type
            
            img_name = ""
            for p in img_dir.glob(_name + ".*"):
                img_name = p.name
                break
            
            if not img_name:
                logger.warning(f"图片 {theme}/{_type}/{_name} 不存在！")
                return False, f"图片 {theme}/{_type}/{_name} 不存在，请检查资源完整性！", "", True
            
            img_path = img_dir / img_name
            with PIL.Image.open(img_path) as img:
                name_cn: str = card_info.get("name_cn")
                meaning = card_info.get("meaning")
                is_upright = random.random() < 0.5
                text = f"「{name_cn}{'正位' if is_upright else '逆位'}」「{meaning['up' if is_upright else 'down']}」\n"
                if not is_upright:
                    rotated_img_name = f"{_name}_rotated.png"
                    rotated_img_path = img_dir / rotated_img_name
                    if not rotated_img_path.exists():
                        img = img.rotate(180)
                        img.save(rotated_img_path, format="png")
                        logger.info(f"保存旋转后的图片: {rotated_img_path}")
                    else:
                        logger.info(f"使用已存在的旋转图片: {rotated_img_path}")
                    final_path = str(rotated_img_path.resolve())
                else:
                    final_path = str(img_path.resolve())
                
                if not os.path.exists(final_path):
                    logger.error(f"图片文件不存在: {final_path}")
                    return False, f"图片文件 {final_path} 不存在！", "", True
                logger.info(f"使用图片路径: {final_path}")
                return True, text, final_path, is_upright
        except Exception as e:
            logger.error(f"处理图片失败: {str(e)}")
            return False, f"处理塔罗牌图片失败: {str(e)}", "", True

    async def _match_formation(self, text: str, all_formations: Dict) -> str:
        text = text.strip().lower()
        formation_names = list(all_formations.keys())
        if not formation_names:
            raise Exception("无可用牌阵")
        keywords = ["情感", "爱情", "关系", "事业", "工作", "未来", "过去", "现状", "处境", "挑战", "建议"]
        for formation in formation_names:
            for keyword in keywords:
                sample_rep = all_formations[formation].get("representations", [[""]])[0]
                if keyword in text and keyword in " ".join(sample_rep).lower():
                    logger.info(f"模糊匹配成功：用户输入 '{text}' 匹配到牌阵 '{formation}'")
                    return formation
        prompt = f"用户输入了以下占卜指令：'{text}'。请根据输入内容，从以下牌阵中选择一个最匹配的牌阵并返回其名称（仅返回名称，无需解释）：\n{', '.join(formation_names)}\n如果无法明确匹配，返回 '随机选择'。"
        try:
            llm_response = await self.context.get_using_provider().text_chat(
                prompt=prompt,
                session_id=None,
                contexts=[],
                image_urls=[],
                system_prompt="你是一个塔罗牌专家，擅长根据用户意图选择合适的牌阵。"
            )
            matched_formation = llm_response.completion_text.strip()
            if matched_formation == "随机选择" or matched_formation not in formation_names:
                logger.info(f"AI 匹配失败或返回随机选择，用户输入: '{text}'")
                return random.choice(formation_names)
            logger.info(f"AI 匹配成功：用户输入 '{text}' 匹配到牌阵 '{matched_formation}'")
            return matched_formation
        except Exception as e:
            logger.error(f"AI 匹配牌阵失败: {str(e)}")
            return random.choice(formation_names)

    async def _generate_ai_interpretation(self, formation_name: str, cards_info: List[Dict], representations: List[str], is_upright_list: List[bool], user_input: str) -> str:
        prompt = f"你是一位专业的塔罗牌占卜师，用户输入了以下完整占卜指令：'{user_input}'。\n请根据以下信息为用户提供详细的占卜结果解析：\n\n"
        prompt += f"牌阵：{formation_name}\n"
        prompt += "抽到的牌及位置：\n"
        for i, (card, rep, is_upright) in enumerate(zip(cards_info, representations, is_upright_list)):
            position = f"第{i+1}张牌「{rep}」"
            card_text = f"「{card['name_cn']}{'正位' if is_upright else '逆位'}」「{card['meaning']['up' if is_upright else 'down']}」"
            prompt += f"{position}: {card_text}\n"
        prompt += (
            f"\n请结合用户指令（'{user_input}'），分析牌阵的含义和每张牌的具体位置，提供一个连贯且可执行的解析。"
            "请用 Markdown 输出，结构至少包含：\n"
            "## 核心结论\n"
            "## 位置解读\n"
            "## 行动建议\n"
            "每个小节 2-4 条要点，语气温和、具体，避免空话。"
        )
        try:
            llm_response = await self.context.get_using_provider().text_chat(
                prompt=prompt,
                session_id=None,
                contexts=[],
                image_urls=[],
                system_prompt="你是一个专业的塔罗牌占卜师，擅长提供深入且简洁的解析。"
            )
            return llm_response.completion_text.strip()
        except Exception as e:
            logger.error(f"生成 AI 解析失败: {str(e)}")
            return "抱歉，AI 解析生成失败，请稍后再试。"

    async def _create_pending_session(self, event: AstrMessageEvent, user_input: str, is_single: bool):
        self._cleanup_pending_sessions()
        question = self._normalize_question(user_input)
        theme = self.pick_theme()
        all_cards, all_formations = self._load_tarot_content()

        if is_single:
            formation_name = "单张牌阵"
            cards_num = 1
            is_cut = False
            representations = ["当前情况"]
        else:
            formation_name = await self._match_formation(question, all_formations)
            formation = all_formations.get(formation_name)
            if not formation:
                formation_name = random.choice(list(all_formations.keys()))
                formation = all_formations.get(formation_name, {})
            cards_num = int(formation.get("cards_num", 3))
            is_cut = bool(formation.get("is_cut", False))
            rep_candidates = formation.get("representations") or []
            selected_rep = random.choice(rep_candidates) if rep_candidates else []
            representations = self._normalize_representations(selected_rep, cards_num)

        draw_pool = self._build_draw_pool(all_cards, theme, cards_num)
        session_key = self._build_session_key(event)
        self.pending_sessions[session_key] = {
            "created_at": time.time(),
            "session_key": session_key,
            "question": question,
            "theme": theme,
            "formation_name": formation_name,
            "cards_num": cards_num,
            "is_cut": is_cut,
            "representations": representations,
            "draw_pool": draw_pool,
            "pool_size": len(draw_pool),
            "is_single": is_single,
            "group_id": self._safe_event_call(event, "get_group_id"),
            "user_id": self._safe_event_call(event, "get_sender_id")
            or self._safe_event_call(event, "get_user_id")
            or "unknown-user",
        }
        return self.pending_sessions[session_key]

    async def divine(self, event: AstrMessageEvent, user_input: str = ""):
        try:
            session = await self._create_pending_session(event, user_input, is_single=False)
            yield event.plain_result(self._build_preparation_message(session["question"]))
            await asyncio.sleep(1)
            yield event.plain_result("洗牌完成，正在切牌并锁定牌阵...")
            yield event.plain_result(
                self._build_draw_prompt(
                    formation_name=session["formation_name"],
                    theme_name=session["theme"],
                    cards_num=session["cards_num"],
                    pool_size=session["pool_size"],
                    representations=session["representations"],
                    is_cut=session["is_cut"],
                    is_single=False,
                )
            )
        except Exception as e:
            logger.error(f"占卜过程出错: {str(e)}")
            yield event.plain_result(f"占卜失败: {str(e)}")

    async def onetime_divine(self, event: AstrMessageEvent, user_input: str = ""):
        try:
            session = await self._create_pending_session(event, user_input, is_single=True)
            yield event.plain_result(self._build_preparation_message(session["question"]))
            await asyncio.sleep(1)
            yield event.plain_result("洗牌完成，已进入单张抽牌流程。")
            yield event.plain_result(
                self._build_draw_prompt(
                    formation_name=session["formation_name"],
                    theme_name=session["theme"],
                    cards_num=session["cards_num"],
                    pool_size=session["pool_size"],
                    representations=session["representations"],
                    is_cut=session["is_cut"],
                    is_single=True,
                )
            )
        except Exception as e:
            logger.error(f"单张占卜出错: {str(e)}")
            yield event.plain_result(f"单张占卜失败: {str(e)}")

    async def _reveal_cards(
        self,
        event: AstrMessageEvent,
        session: Dict[str, Any],
        selected_cards: List[Dict[str, Any]],
        selected_numbers: List[int],
    ):
        cards_num = session["cards_num"]
        representations = session["representations"]
        is_cut = session["is_cut"]
        theme = session["theme"]
        question = session["question"]
        formation_name = session["formation_name"]
        bot_name = self.context.get_config().get("nickname", "占卜师")

        is_upright_list: List[bool] = []
        record_cards: List[Dict[str, Any]] = []
        analysis_markdown = ""
        group_id = self._safe_event_call(event, "get_group_id")
        is_group_chat = group_id is not None

        if self.is_chain_reply and is_group_chat:
            chain = Nodes([])
            for i in range(cards_num):
                position = representations[i]
                header = f"切牌「{position}」\n" if (is_cut and i == cards_num - 1) else f"第{i + 1}张牌「{position}」\n"
                flag, text, img_path, is_upright = await self._get_text_and_image(theme, selected_cards[i])
                if not flag:
                    yield event.plain_result(text)
                    return
                is_upright_list.append(is_upright)
                node = Node(
                    uin=event.get_self_id(),
                    name=bot_name,
                    content=[Plain(header + text), Image.fromFileSystem(img_path)],
                )
                chain.nodes.append(node)
                record_cards.append(
                    {
                        "position": position,
                        "name": selected_cards[i].get("name_cn", "未知牌"),
                        "orientation": "正位" if is_upright else "逆位",
                        "meaning": selected_cards[i].get("meaning", {}).get("up" if is_upright else "down", ""),
                    }
                )
            interpretation = await self._generate_ai_interpretation(
                formation_name, selected_cards, representations, is_upright_list, question
            )
            analysis_markdown = self._build_interpretation_markdown(
                question=question,
                formation_name=formation_name,
                record_cards=record_cards,
                interpretation=interpretation,
            )
            analysis_card_path = await self._render_markdown_card(analysis_markdown)
            if self.include_ai_in_chain:
                if analysis_card_path:
                    chain.nodes.append(
                        Node(
                            uin=event.get_self_id(),
                            name=bot_name,
                            content=[
                                Plain("\n“属于你的占卜分析卡片（Markdown）”"),
                                Image.fromFileSystem(analysis_card_path),
                            ],
                        )
                    )
                else:
                    chain.nodes.append(
                        Node(
                            uin=event.get_self_id(),
                            name=bot_name,
                            content=[Plain(f"\n“属于你的占卜分析！”\n{interpretation}")],
                        )
                    )
            if not chain.nodes:
                yield event.plain_result("无法生成塔罗牌结果，请稍后重试")
                return
            yield event.chain_result([chain])
            if not self.include_ai_in_chain:
                if analysis_card_path:
                    yield event.chain_result(
                        [
                            Plain("\n“属于你的占卜分析卡片（Markdown）”"),
                            Image.fromFileSystem(analysis_card_path),
                        ]
                    )
                else:
                    yield event.plain_result(f"\n“属于你的占卜分析！”\n{interpretation}")
        else:
            for i in range(cards_num):
                position = representations[i]
                header = f"切牌「{position}」\n" if (is_cut and i == cards_num - 1) else f"第{i + 1}张牌「{position}」\n"
                flag, text, img_path, is_upright = await self._get_text_and_image(theme, selected_cards[i])
                if not flag:
                    yield event.plain_result(text)
                    return
                is_upright_list.append(is_upright)
                yield event.chain_result([Plain(header + text), Image.fromFileSystem(img_path)])
                record_cards.append(
                    {
                        "position": position,
                        "name": selected_cards[i].get("name_cn", "未知牌"),
                        "orientation": "正位" if is_upright else "逆位",
                        "meaning": selected_cards[i].get("meaning", {}).get("up" if is_upright else "down", ""),
                    }
                )
                if i < cards_num - 1:
                    await asyncio.sleep(1)
            interpretation = await self._generate_ai_interpretation(
                formation_name, selected_cards, representations, is_upright_list, question
            )
            analysis_markdown = self._build_interpretation_markdown(
                question=question,
                formation_name=formation_name,
                record_cards=record_cards,
                interpretation=interpretation,
            )
            analysis_card_path = await self._render_markdown_card(analysis_markdown)
            if analysis_card_path:
                yield event.chain_result(
                    [
                        Plain("\n“属于你的占卜分析卡片（Markdown）”"),
                        Image.fromFileSystem(analysis_card_path),
                    ]
                )
            else:
                yield event.plain_result(f"\n“属于你的占卜分析！”\n{interpretation}")

        await self._append_record(
            {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "session_key": session["session_key"],
                "group_id": session["group_id"],
                "user_id": session["user_id"],
                "question": question,
                "theme": theme,
                "formation": formation_name,
                "selected_numbers": selected_numbers,
                "cards": record_cards,
                "overall_interpretation": interpretation,
                "overall_interpretation_markdown": analysis_markdown,
            }
        )

    async def draw_by_numbers(self, event: AstrMessageEvent, text: str = ""):
        try:
            self._cleanup_pending_sessions()
            session_key = self._build_session_key(event)
            session = self.pending_sessions.get(session_key)
            if not session:
                yield event.plain_result("当前没有待抽牌会话，请先发送 /tarot 你的问题 或 塔罗牌 你的问题。")
                return

            if time.time() - session.get("created_at", 0) > self.pending_expire_seconds:
                self.pending_sessions.pop(session_key, None)
                yield event.plain_result("抽牌会话已超时，请重新发起占卜。")
                return

            selected_numbers = self._parse_draw_numbers(text)
            cards_num = session["cards_num"]
            pool_size = session["pool_size"]
            if len(selected_numbers) != cards_num:
                yield event.plain_result(
                    f"需要选择 {cards_num} 个编号，当前收到 {len(selected_numbers)} 个。示例：抽牌 {' '.join(str(i + 1) for i in range(cards_num))}"
                )
                return
            if len(set(selected_numbers)) != len(selected_numbers):
                yield event.plain_result("抽牌编号不能重复，请重新输入。")
                return
            if any(num < 1 or num > pool_size for num in selected_numbers):
                yield event.plain_result(f"编号超出范围，请在 1-{pool_size} 之间选择。")
                return

            selected_cards = [session["draw_pool"][num - 1] for num in selected_numbers]
            self.pending_sessions.pop(session_key, None)
            yield event.plain_result(f"已抽取编号：{' '.join(str(num) for num in selected_numbers)}，正在翻牌解读...")
            async for result in self._reveal_cards(event, session, selected_cards, selected_numbers):
                yield result
        except Exception as e:
            logger.error("抽牌流程失败: %s", str(e))
            yield event.plain_result(f"抽牌失败: {str(e)}")

    async def show_records(self, event: AstrMessageEvent, text: str = ""):
        try:
            if not self.records_file.exists():
                yield event.plain_result("暂无占卜记录。")
                return

            requested = self._parse_draw_numbers(text)
            limit = requested[0] if requested else 3
            limit = max(1, min(10, limit))

            session_key = self._build_session_key(event)
            with open(self.records_file, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]

            records: List[Dict[str, Any]] = []
            for line in reversed(lines):
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                if record.get("session_key") == session_key:
                    records.append(record)
                if len(records) >= limit:
                    break

            if not records:
                yield event.plain_result("暂无你的占卜记录。")
                return

            chunks = []
            for idx, record in enumerate(records, start=1):
                cards_text = "、".join(
                    f"{card.get('position', '位置')}:{card.get('name', '未知')}{card.get('orientation', '')}"
                    for card in record.get("cards", [])
                )
                number_text = " ".join(str(num) for num in record.get("selected_numbers", []))
                chunks.append(
                    f"{idx}. {record.get('created_at', '-') }\n"
                    f"问题：{record.get('question', '-') }\n"
                    f"牌阵：{record.get('formation', '-') }\n"
                    f"抽牌编号：{number_text or '-'}\n"
                    f"牌面：{cards_text or '-'}"
                )

            yield event.plain_result("最近占卜记录：\n\n" + "\n\n".join(chunks))
        except Exception as e:
            logger.error("读取占卜记录失败: %s", str(e))
            yield event.plain_result(f"读取占卜记录失败: {str(e)}")

    def switch_chain_reply(self, new_state: bool) -> str:
        self.is_chain_reply = new_state
        logger.info(f"群聊转发模式已切换为: {new_state}")
        return "占卜群聊转发模式已开启~" if new_state else "占卜群聊转发模式已关闭~"

@register("tarot", "Elysium-Seeker", "赛博塔罗牌占卜插件", "0.2.15")
class TarotPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.tarot = Tarot(context, config)

    def _help_message(self) -> str:
        return (
            "赛博塔罗牌 v0.2.15\n"
            "[/tarot 问题] 进入多牌占卜流程，先洗牌选阵，再输入编号抽牌\n"
            "[/tarot] 不带问题时会引导你先提问\n"
            "[主题选择] 默认强制使用 BilibiliTarot（可通过 force_theme 配置）\n"
            "[抽牌池默认规则] 默认展示该主题下全部可抽牌编号\n"
            "[编号规则] 编号从 1 开始，不存在 0 号牌\n"
            "[抽牌池配置] full_draw_pool=true 时始终全牌池\n"
            "[分析输出] 整体解读将渲染为 Markdown 风格占卜卡片\n"
            "[乱码修复] 可设置 markdown_card_font_path 指向中文字体；若无可用字体将自动回退纯文本\n"
            "[自动抽牌] 有待抽牌会话时，直接回复编号（如 1 5 9）即可\n"
            "[命令兜底] 若平台拦截纯数字消息，可用 /tarot 1 5 9 直接抽牌\n"
            "[塔罗牌 问题] 进入单张抽牌流程\n"
            "[抽牌 编号1 编号2 ...] 按提示完成抽牌并获取牌面+整体分析卡片\n"
            "[占卜记录 数量] 查看最近记录（默认 3 条，最多 10 条）\n"
            "[开启/关闭群聊转发] 切换群聊转发模式"
        )

    @staticmethod
    def _is_draw_numbers_message(text: str) -> bool:
        return bool(re.match(r"^\s*\d+(?:[\s,，]+\d+)*\s*$", text or ""))

    def _extract_message_text(self, event: AstrMessageEvent, fallback_text: str = "") -> str:
        if (fallback_text or "").strip():
            return fallback_text.strip()

        event_attrs = ["message_str", "raw_message", "text", "message_text"]
        for attr in event_attrs:
            value = getattr(event, attr, None)
            if isinstance(value, str) and value.strip():
                return value.strip()

        message_obj = getattr(event, "message_obj", None)
        if message_obj is not None:
            for attr in ("message_str", "raw_message", "text", "message"):
                value = getattr(message_obj, attr, None)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        getter_names = ["get_message_str", "get_plain_text", "get_message_text", "get_raw_message", "get_message"]
        for getter_name in getter_names:
            getter = getattr(event, getter_name, None)
            if callable(getter):
                try:
                    value = getter()
                except Exception:
                    continue
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    @command("tarot")
    async def tarot_handler(self, event: AstrMessageEvent, text: str = ""):
        try:
            user_text = (text or "").strip()

            if self._is_draw_numbers_message(user_text):
                if self.tarot.has_pending_session(event):
                    async for result in self.tarot.draw_by_numbers(event, user_text):
                        yield result
                else:
                    yield event.plain_result(
                        "当前没有待抽牌会话，请先发送 /tarot 你的问题 发起占卜。"
                    )
                event.stop_event()
                return

            if not user_text:
                yield event.plain_result(
                    "请先告诉我你的问题，再进行占卜。\n"
                    "示例：/tarot 我目前的感情状况如何？\n"
                    "建议使用具体、开放式的问题。"
                )
            elif user_text in {"帮助", "help", "Help", "HELP"}:
                yield event.plain_result(self._help_message())
            else:
                async for result in self.tarot.divine(event, user_text):
                    yield result
            event.stop_event()
        except Exception as e:
            logger.error(f"处理 /tarot 命令失败: {str(e)}")
            yield event.plain_result(f"/tarot 命令执行失败: {str(e)}")

    @command("塔罗牌")
    async def onetime_divine_handler(self, event: AstrMessageEvent, text: str = ""):
        try:
            if (text or "").strip() in {"帮助", "help", "Help", "HELP"}:
                yield event.plain_result(self._help_message())
            else:
                async for result in self.tarot.onetime_divine(event, text):
                    yield result
            event.stop_event()
        except Exception as e:
            logger.error(f"处理塔罗牌命令失败: {str(e)}")
            yield event.plain_result(f"塔罗牌命令执行失败: {str(e)}")

    @command("抽牌")
    async def draw_handler(self, event: AstrMessageEvent, text: str = ""):
        try:
            async for result in self.tarot.draw_by_numbers(event, text):
                yield result
            event.stop_event()
        except Exception as e:
            logger.error("处理抽牌命令失败: %s", str(e))
            yield event.plain_result(f"抽牌命令执行失败: {str(e)}")

    @filter.regex(r"^\s*\d+(?:[\s,，]+\d+)*\s*$")
    async def draw_by_reply_handler(self, event: AstrMessageEvent, text: str = ""):
        try:
            if not self.tarot.has_pending_session(event):
                return
            message_text = self._extract_message_text(event, text)
            if not message_text:
                return
            async for result in self.tarot.draw_by_numbers(event, message_text):
                yield result
            event.stop_event()
        except Exception as e:
            logger.error("处理编号直回抽牌失败: %s", str(e))
            yield event.plain_result(f"编号直回抽牌失败: {str(e)}")

    @command("占卜记录")
    async def records_handler(self, event: AstrMessageEvent, text: str = ""):
        try:
            async for result in self.tarot.show_records(event, text):
                yield result
            event.stop_event()
        except Exception as e:
            logger.error("处理占卜记录命令失败: %s", str(e))
            yield event.plain_result(f"占卜记录命令执行失败: {str(e)}")

    @command("开启群聊转发")
    async def enable_chain_reply(self, event: AstrMessageEvent, text: str = ""):
        try:
            msg = self.tarot.switch_chain_reply(True)
            yield event.plain_result(msg)
            event.stop_event()
        except Exception as e:
            logger.error(f"开启群聊转发失败: {str(e)}")
            yield event.plain_result(f"开启群聊转发失败: {str(e)}")

    @command("关闭群聊转发")
    async def disable_chain_reply(self, event: AstrMessageEvent, text: str = ""):
        try:
            msg = self.tarot.switch_chain_reply(False)
            yield event.plain_result(msg)
            event.stop_event()
        except Exception as e:
            logger.error(f"关闭群聊转发失败: {str(e)}")
            yield event.plain_result(f"关闭群聊转发失败: {str(e)}")