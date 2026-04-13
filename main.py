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
        self.followup_expire_seconds: int = int(config.get("followup_expire_seconds", 1800))
        self.enable_record: bool = config.get("enable_record", True)
        self.full_draw_pool: bool = config.get("full_draw_pool", True)
        self.draw_pool_factor: int = max(0, int(config.get("draw_pool_factor", 0)))
        raw_force_theme = config.get("force_theme", "BilibiliTarot")
        self.force_theme: str = str(raw_force_theme).strip() if raw_force_theme is not None else ""
        self.enable_markdown_card: bool = config.get("enable_markdown_card", True)
        raw_card_font_path = config.get("markdown_card_font_path", "")
        self.markdown_card_font_path: str = str(raw_card_font_path).strip() if raw_card_font_path is not None else ""
        self.pending_sessions: Dict[str, Dict[str, Any]] = {}
        self.followup_sessions: Dict[str, Dict[str, Any]] = {}
        self.pending_followup_draws: Dict[str, Dict[str, Any]] = {}
        self.record_lock = asyncio.Lock()
        self.data_dir: Path = self._resolve_data_dir(context)
        self.records_file: Path = self.data_dir / "divination_records.jsonl"

        os.makedirs(self.resource_path, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        if not self.tarot_json.exists():
            logger.error("tarot.json 文件缺失，请确保资源完整！")
            raise Exception("tarot.json 文件缺失，请确保资源完整！")
        logger.info(
            "Tarot 插件初始化完成，资源路径: %s, AI 解析加入转发: %s, 记录功能: %s, 全牌池: %s, 抽牌池倍率: %s, 强制主题: %s, Markdown 卡片: %s, 卡片字体: %s, 追问上下文过期: %ss",
            self.resource_path,
            self.include_ai_in_chain,
            self.enable_record,
            self.full_draw_pool,
            self.draw_pool_factor,
            self.force_theme or "<随机>",
            self.enable_markdown_card,
            self.markdown_card_font_path or "<自动探测>",
            self.followup_expire_seconds,
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

    def has_pending_followup_draw(self, event: AstrMessageEvent) -> bool:
        self._cleanup_pending_followup_draws()
        session_key = self._build_session_key(event)
        session = self.pending_followup_draws.get(session_key)
        if not session:
            return False
        if time.time() - session.get("created_at", 0) > self.pending_expire_seconds:
            self.pending_followup_draws.pop(session_key, None)
            return False
        return True

    def _cleanup_pending_followup_draws(self):
        now = time.time()
        expired_keys = [
            key
            for key, session in self.pending_followup_draws.items()
            if now - session.get("created_at", now) > self.pending_expire_seconds
        ]
        for key in expired_keys:
            self.pending_followup_draws.pop(key, None)

    def has_followup_session(self, event: AstrMessageEvent) -> bool:
        self._cleanup_followup_sessions()
        session_key = self._build_session_key(event)
        session = self.followup_sessions.get(session_key)
        if not session:
            return False
        if time.time() - session.get("created_at", 0) > self.followup_expire_seconds:
            self.followup_sessions.pop(session_key, None)
            return False
        return True

    def _cleanup_followup_sessions(self):
        now = time.time()
        expired_keys = [
            key
            for key, session in self.followup_sessions.items()
            if now - session.get("created_at", now) > self.followup_expire_seconds
        ]
        for key in expired_keys:
            self.followup_sessions.pop(key, None)

    @staticmethod
    def _normalize_compare_text(text: str) -> str:
        return re.sub(r"\s+", " ", text or "").strip().lower()

    def get_followup_session(self, event: AstrMessageEvent) -> Optional[Dict[str, Any]]:
        self._cleanup_followup_sessions()
        session_key = self._build_session_key(event)
        session = self.followup_sessions.get(session_key)
        if not session:
            return None
        if time.time() - session.get("created_at", 0) > self.followup_expire_seconds:
            self.followup_sessions.pop(session_key, None)
            return None
        return session

    def get_same_question_redraw_hint(self, event: AstrMessageEvent, question: str) -> Optional[str]:
        session = self.get_followup_session(event)
        if not session:
            return None
        new_q = self._normalize_compare_text(question)
        old_q = self._normalize_compare_text(session.get("question", ""))
        if not new_q or not old_q:
            return None
        if new_q != old_q:
            return None
        return (
            "这是同一个问题，建议不要重复抽牌。\n"
            "你现在更适合：\n"
            "1) /追问 你的问题（系统会提示你从剩余牌中补抽1-2张说明牌）\n"
            "2) 按提示输入编号完成说明牌抽取\n"
            "如果是全新问题，再用 /tarot 发起新占卜。"
        )

    @staticmethod
    def _format_number_list(numbers: List[int]) -> str:
        numbers = sorted(numbers)
        return "\n".join(" ".join(str(n) for n in numbers[i:i + 10]) for i in range(0, len(numbers), 10))

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

    def _candidate_font_paths(self, bold: bool = False) -> List[str]:
        candidates: List[str] = []
        if self.markdown_card_font_path:
            custom_path = Path(self.markdown_card_font_path)
            if custom_path.is_dir():
                for pattern in ("*.ttf", "*.ttc", "*.otf"):
                    for font_file in sorted(custom_path.glob(pattern)):
                        candidates.append(str(font_file))
            else:
                candidates.append(str(custom_path))

        local_font_dir = Path(__file__).parent / "resources" / "fonts"
        if local_font_dir.exists():
            preferred_bundled = [
                local_font_dir / "NotoSerifSC-VF.ttf",
                local_font_dir / "NotoSansSC-VF.ttf",
            ]
            for font_file in preferred_bundled:
                if font_file.exists():
                    candidates.append(str(font_file))

            for pattern in ("*.ttf", "*.ttc", "*.otf"):
                for font_file in sorted(local_font_dir.glob(pattern)):
                    candidates.append(str(font_file))

        if os.name == "nt":
            windows_font_dir = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
            if bold:
                candidates.extend(
                    [
                        str(windows_font_dir / "msyhbd.ttc"),
                        str(windows_font_dir / "msyhbd.ttf"),
                        str(windows_font_dir / "Dengb.ttf"),
                        str(windows_font_dir / "simhei.ttf"),
                        str(windows_font_dir / "simkai.ttf"),
                        str(windows_font_dir / "simsun.ttc"),
                    ]
                )
            else:
                candidates.extend(
                    [
                        str(windows_font_dir / "msyh.ttc"),
                        str(windows_font_dir / "msyh.ttf"),
                        str(windows_font_dir / "Deng.ttf"),
                        str(windows_font_dir / "simhei.ttf"),
                        str(windows_font_dir / "simsun.ttc"),
                        str(windows_font_dir / "simkai.ttf"),
                    ]
                )
        else:
            if bold:
                candidates.extend(
                    [
                        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
                        "/usr/share/fonts/truetype/noto/NotoSerifCJK-Bold.ttc",
                        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc",
                        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                        "/usr/share/fonts/noto-cjk/NotoSerifCJK-Bold.ttc",
                        "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",
                        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                        "/usr/share/fonts/opentype/adobe-source-han-sans/SourceHanSansCN-Bold.otf",
                    ]
                )
            else:
                candidates.extend(
                    [
                        "/usr/share/fonts/truetype/noto/NotoSerifCJK-Regular.ttc",
                        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
                        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
                        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                        "/usr/share/fonts/noto-cjk/NotoSerifCJK-Regular.ttc",
                        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                        "/usr/share/fonts/opentype/adobe-source-han-sans/SourceHanSansCN-Regular.otf",
                    ]
                )

        # 去重并保序。
        unique_paths: List[str] = []
        seen: set = set()
        for path in candidates:
            if path and path not in seen:
                unique_paths.append(path)
                seen.add(path)
        return unique_paths

    def _load_font(self, size: int, bold: bool = False):
        for font_path in self._candidate_font_paths(bold=bold):
            try:
                if Path(font_path).exists():
                    return PIL.ImageFont.truetype(font_path, size)
            except Exception:
                continue
        return None

    @staticmethod
    def _strip_inline_markdown(text: str) -> str:
        cleaned = text or ""
        cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
        cleaned = re.sub(r"__([^_]+)__", r"\1", cleaned)
        cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
        cleaned = re.sub(r"_([^_]+)_", r"\1", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        return cleaned.strip()

    @staticmethod
    def _measure_text(draw: PIL.ImageDraw.ImageDraw, text: str, font) -> Tuple[int, int]:
        value = text if text else " "
        left, top, right, bottom = draw.textbbox((0, 0), value, font=font)
        return max(1, right - left), max(1, bottom - top)

    def _wrap_text_lines(self, draw: PIL.ImageDraw.ImageDraw, text: str, font, max_width: int) -> List[str]:
        clean_text = (text or "").strip()
        if not clean_text:
            return [""]

        lines: List[str] = []
        current = ""
        for ch in clean_text:
            test = current + ch
            width, _ = self._measure_text(draw, test, font)
            if width <= max_width or not current:
                current = test
            else:
                lines.append(current.rstrip())
                current = ch
        if current:
            lines.append(current.rstrip())
        return lines

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
            width = 1080
            outer_padding = 36
            panel_padding = 42
            max_text_width = width - (outer_padding * 2) - (panel_padding * 2)

            font_h1 = self._load_font(50, bold=True)
            font_h2 = self._load_font(38, bold=True)
            font_h3 = self._load_font(32, bold=True)
            font_body = self._load_font(28, bold=False)

            if not all([font_h1, font_h2, font_h3, font_body]):
                logger.warning(
                    "Markdown 卡片渲染跳过：未找到可用中文字体，已回退纯文本。请配置 markdown_card_font_path 或在系统安装 Noto CJK/WenQuanYi 字体。"
                )
                return None

            measure = PIL.Image.new("RGB", (width, 20), (0, 0, 0))
            measure_draw = PIL.ImageDraw.Draw(measure)

            layout_items: List[Dict[str, Any]] = []
            content_height = 0

            for raw in markdown_text.splitlines():
                line = raw.strip()
                if not line:
                    spacer = 14
                    layout_items.append({"kind": "space", "height": spacer})
                    content_height += spacer
                    continue

                if line == "---":
                    divider_h = 32
                    layout_items.append({"kind": "divider", "height": divider_h})
                    content_height += divider_h
                    continue

                font = font_body
                color = (224, 214, 197)
                line_gap = 12
                prefix = ""
                text = line
                indent = 0

                if line.startswith("# "):
                    text = line[2:].strip()
                    font = font_h1
                    color = (233, 194, 112)
                    line_gap = 20
                elif line.startswith("## "):
                    text = line[3:].strip()
                    font = font_h2
                    color = (214, 173, 98)
                    line_gap = 16
                elif line.startswith("### "):
                    text = line[4:].strip()
                    font = font_h3
                    color = (196, 159, 95)
                    line_gap = 14
                elif line.startswith("- ") or line.startswith("* "):
                    text = line[2:].strip()
                    prefix = "✦ "
                    color = (216, 204, 186)
                    line_gap = 10
                    indent = 30

                clean = self._strip_inline_markdown(text)
                wrapped = self._wrap_text_lines(measure_draw, clean, font, max_text_width - indent)
                _, sample_h = self._measure_text(measure_draw, "塔罗", font)
                line_height = max(sample_h + 10, 32)

                for idx, wrapped_line in enumerate(wrapped):
                    output = wrapped_line
                    if prefix:
                        output = (prefix if idx == 0 else "  ") + wrapped_line
                    layout_items.append(
                        {
                            "kind": "text",
                            "text": output,
                            "font": font,
                            "color": color,
                            "height": line_height,
                        }
                    )
                    content_height += line_height
                content_height += line_gap

            height = max(760, content_height + (outer_padding * 2) + (panel_padding * 2))

            img = PIL.Image.new("RGB", (width, height), (14, 12, 28))
            draw = PIL.ImageDraw.Draw(img)
            for y in range(height):
                ratio = y / max(1, height - 1)
                r = int(14 + (30 - 14) * ratio)
                g = int(12 + (22 - 12) * ratio)
                b = int(28 + (45 - 28) * ratio)
                draw.line([(0, y), (width, y)], fill=(r, g, b))

            panel = (outer_padding, outer_padding, width - outer_padding, height - outer_padding)
            draw.rounded_rectangle(panel, radius=28, fill=(34, 27, 50), outline=(171, 134, 78), width=3)
            inner = (panel[0] + 10, panel[1] + 10, panel[2] - 10, panel[3] - 10)
            draw.rounded_rectangle(inner, radius=22, outline=(120, 97, 58), width=1)

            deco_points = [
                (outer_padding + 18, outer_padding + 18),
                (width - outer_padding - 22, outer_padding + 18),
                (outer_padding + 18, height - outer_padding - 22),
                (width - outer_padding - 22, height - outer_padding - 22),
            ]
            for x, y in deco_points:
                draw.ellipse((x, y, x + 6, y + 6), fill=(219, 178, 105))

            x = outer_padding + panel_padding
            y = outer_padding + panel_padding
            for item in layout_items:
                if item["kind"] == "space":
                    y += item["height"]
                    continue
                if item["kind"] == "divider":
                    y += 10
                    draw.line((x, y, width - outer_padding - panel_padding, y), fill=(180, 145, 88), width=2)
                    y += item["height"] - 10
                    continue
                draw.text((x, y), item["text"], font=item["font"], fill=item["color"])
                y += item["height"]

            card_dir = self.data_dir / "analysis_cards"
            os.makedirs(card_dir, exist_ok=True)
            card_path = card_dir / f"reading_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"

            img.save(card_path, format="PNG")
            return str(card_path.resolve())
        except Exception as e:
            logger.error("Markdown Pillow 渲染失败，已回退纯文本: %s", str(e))
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

    async def _generate_followup_interpretation(
        self,
        base_question: str,
        formation_name: str,
        cards: List[Dict[str, Any]],
        latest_interpretation: str,
        followup_question: str,
        followup_history: List[Dict[str, Any]],
        supplement_cards: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        cards_text = "\n".join(
            f"- {card.get('position', '位置')}：{card.get('name', '未知牌')}{card.get('orientation', '')} · {card.get('meaning', '')}"
            for card in cards
        )
        supplement_cards = supplement_cards or []
        supplement_text = ""
        if supplement_cards:
            supplement_text = "\n".join(
                f"- {card.get('position', '补充牌')}：{card.get('name', '未知牌')}{card.get('orientation', '')} · {card.get('meaning', '')}"
                for card in supplement_cards
            )
        history_text = ""
        if followup_history:
            history_items = []
            for item in followup_history[-3:]:
                history_items.append(f"- 追问：{item.get('question', '')}\n  回答：{item.get('answer', '')}")
            history_text = "\n".join(history_items)

        prompt = (
            "你是一位专业的塔罗牌占卜师。现在用户基于上一轮占卜继续追问。\n"
            f"原始问题：{base_question}\n"
            f"牌阵：{formation_name}\n"
            f"牌面：\n{cards_text}\n\n"
            f"上一轮解读摘要：\n{latest_interpretation}\n\n"
        )
        if supplement_cards:
            prompt += (
                "本次追问补充抽取了说明牌。\n"
                f"说明牌：\n{supplement_text}\n\n"
                "请把说明牌与原有牌面联合解读，不要孤立分析新牌。\n\n"
            )
        else:
            prompt += "本次不抽新牌，仅基于原牌进行深入追问解读。\n\n"
        if history_text:
            prompt += f"历史追问（最近 3 条）：\n{history_text}\n\n"
        prompt += (
            f"本次追问：{followup_question}\n\n"
            "请在不改变牌面的前提下，结合上一轮解读做更聚焦的补充分析。"
            "请用 Markdown 输出，结构至少包含：\n"
            "## 追问结论\n"
            "## 关键依据\n"
            "## 可执行建议\n"
            "每个小节 2-4 条要点，避免空泛表达。"
        )

        try:
            llm_response = await self.context.get_using_provider().text_chat(
                prompt=prompt,
                session_id=None,
                contexts=[],
                image_urls=[],
                system_prompt="你是一个专业的塔罗牌占卜师，擅长连续对话与追问分析。",
            )
            return llm_response.completion_text.strip()
        except Exception as e:
            logger.error("生成追问解析失败: %s", str(e))
            return "抱歉，追问解析生成失败，请稍后再试。"

    def _build_followup_draw_prompt(self, followup_question: str, supplement_count: int, candidate_numbers: List[int]) -> str:
        return (
            "同题追问采用原牌延伸，不会重洗牌。\n"
            f"本次追问：{followup_question}\n"
            f"请从剩余牌中选择 {supplement_count} 个编号作为说明牌。\n"
            "注意：说明牌编号不能与之前已抽编号重复。\n"
            "输入方式：\n"
            "1) 直接回复编号（推荐）\n"
            "2) /追问 编号1 编号2 ...\n"
            f"可选编号（剩余牌）：\n{self._format_number_list(candidate_numbers)}"
        )

    def _take_followup_cards_by_numbers(
        self,
        followup_session: Dict[str, Any],
        selected_numbers: List[int],
    ) -> List[Dict[str, Any]]:
        remaining_entries: List[Dict[str, Any]] = list(followup_session.get("remaining_cards", []))
        entry_map = {int(entry.get("number", -1)): entry for entry in remaining_entries}
        picked_entries = [entry_map[num] for num in selected_numbers if num in entry_map]

        picked_set = set(selected_numbers)
        followup_session["remaining_cards"] = [
            entry for entry in remaining_entries if int(entry.get("number", -1)) not in picked_set
        ]
        return picked_entries

    async def followup(self, event: AstrMessageEvent, user_input: str = ""):
        try:
            followup_question = self._normalize_question(user_input)
            self._cleanup_followup_sessions()
            self._cleanup_pending_followup_draws()
            session_key = self._build_session_key(event)
            followup_session = self.followup_sessions.get(session_key)

            if not followup_session:
                yield event.plain_result("当前没有可追问的占卜上下文，请先完成一轮占卜后再追问。")
                return

            if time.time() - followup_session.get("created_at", 0) > self.followup_expire_seconds:
                self.followup_sessions.pop(session_key, None)
                yield event.plain_result("追问上下文已过期，请重新发起占卜。")
                return

            remaining_cards = list(followup_session.get("remaining_cards", []))
            if not remaining_cards:
                yield event.plain_result("当前牌堆已无剩余可补充的说明牌，请在新问题下重新占卜。")
                return

            supplement_count = random.choice([1, 2])
            if len(remaining_cards) == 1:
                supplement_count = 1

            candidate_numbers = sorted(int(item.get("number", 0)) for item in remaining_cards if int(item.get("number", 0)) > 0)
            if not candidate_numbers:
                yield event.plain_result("剩余牌编号异常，请重新发起占卜。")
                return

            self.pending_followup_draws[session_key] = {
                "created_at": time.time(),
                "followup_question": followup_question,
                "supplement_count": supplement_count,
                "candidate_numbers": candidate_numbers,
            }

            yield event.plain_result(self._build_followup_draw_prompt(followup_question, supplement_count, candidate_numbers))
        except Exception as e:
            logger.error("追问流程失败: %s", str(e))
            yield event.plain_result(f"追问失败: {str(e)}")

    async def draw_followup_by_numbers(self, event: AstrMessageEvent, text: str = ""):
        try:
            self._cleanup_followup_sessions()
            self._cleanup_pending_followup_draws()
            session_key = self._build_session_key(event)

            followup_session = self.followup_sessions.get(session_key)
            if not followup_session:
                yield event.plain_result("当前没有可追问的占卜上下文，请先完成一轮占卜。")
                return

            pending_draw = self.pending_followup_draws.get(session_key)
            if not pending_draw:
                yield event.plain_result("当前没有待补充抽牌的追问，请先发送 /追问 问题。")
                return

            selected_numbers = self._parse_draw_numbers(text)
            supplement_count = int(pending_draw.get("supplement_count", 1))
            if len(selected_numbers) != supplement_count:
                yield event.plain_result(
                    f"本次追问需要选择 {supplement_count} 个编号，当前收到 {len(selected_numbers)} 个。"
                )
                return
            if len(set(selected_numbers)) != len(selected_numbers):
                yield event.plain_result("说明牌编号不能重复，请重新选择。")
                return

            old_numbers = set(followup_session.get("selected_numbers", []))
            if any(num in old_numbers for num in selected_numbers):
                yield event.plain_result("说明牌编号不能与之前已抽牌相同，请重新抽取。")
                return

            candidate_numbers = set(int(num) for num in pending_draw.get("candidate_numbers", []))
            if any(num not in candidate_numbers for num in selected_numbers):
                yield event.plain_result("编号不在本次追问可选范围内，请按提示重新选择。")
                return

            picked_entries = self._take_followup_cards_by_numbers(followup_session, selected_numbers)
            if len(picked_entries) != supplement_count:
                yield event.plain_result("说明牌抽取失败，请重新发起 /追问。")
                return

            base_cards = list(followup_session.get("cards", []))
            formation_name = followup_session.get("formation_name", "未知牌阵")
            base_question = followup_session.get("question", "")
            latest_interpretation = followup_session.get("latest_interpretation", "")
            followup_history = followup_session.get("followups", [])
            theme = followup_session.get("theme", "")
            followup_question = str(pending_draw.get("followup_question", "")).strip() or "我想更深入理解这次占卜"

            supplement_cards: List[Dict[str, Any]] = []
            for idx, entry in enumerate(picked_entries, start=1):
                number = int(entry.get("number", 0))
                card_info = entry.get("card") or {}
                flag, text_out, img_path, is_upright = await self._get_text_and_image(theme, card_info)
                if not flag:
                    yield event.plain_result(text_out)
                    return

                supplement_card = {
                    "position": f"说明牌{idx}（编号{number}）",
                    "name": card_info.get("name_cn", "未知牌"),
                    "orientation": "正位" if is_upright else "逆位",
                    "meaning": card_info.get("meaning", {}).get("up" if is_upright else "down", ""),
                }
                supplement_cards.append(supplement_card)
                yield event.chain_result(
                    [
                        Plain(f"说明牌{idx}（编号{number}）\n{text_out}"),
                        Image.fromFileSystem(img_path),
                    ]
                )

            interpretation = await self._generate_followup_interpretation(
                base_question=base_question,
                formation_name=formation_name,
                cards=base_cards,
                latest_interpretation=latest_interpretation,
                followup_question=followup_question,
                followup_history=followup_history,
                supplement_cards=supplement_cards,
            )

            followup_markdown = self._build_interpretation_markdown(
                question=f"{base_question}（追问：{followup_question}）",
                formation_name=formation_name,
                record_cards=base_cards + supplement_cards,
                interpretation=interpretation,
            )
            analysis_card_path = await self._render_markdown_card(followup_markdown)

            if analysis_card_path:
                yield event.chain_result(
                    [
                        Plain("\n“属于你的追问解读卡片（Markdown）”"),
                        Image.fromFileSystem(analysis_card_path),
                    ]
                )
            else:
                yield event.plain_result(f"\n“属于你的追问解读！”\n{interpretation}")

            followup_entry = {
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "question": followup_question,
                "answer": interpretation,
                "supplement_cards": supplement_cards,
                "supplement_numbers": selected_numbers,
            }
            followup_history.append(followup_entry)
            followup_session["followups"] = followup_history
            followup_session["latest_interpretation"] = interpretation
            followup_session["created_at"] = time.time()
            followup_session["selected_numbers"] = sorted(
                set(followup_session.get("selected_numbers", [])) | set(selected_numbers)
            )
            followup_session["supplement_cards"] = followup_session.get("supplement_cards", []) + supplement_cards

            self.pending_followup_draws.pop(session_key, None)

            await self._append_record(
                {
                    "created_at": datetime.now().isoformat(timespec="seconds"),
                    "session_key": session_key,
                    "group_id": self._safe_event_call(event, "get_group_id"),
                    "user_id": self._safe_event_call(event, "get_sender_id")
                    or self._safe_event_call(event, "get_user_id")
                    or "unknown-user",
                    "question": base_question,
                    "followup_question": followup_question,
                    "theme": theme,
                    "formation": formation_name,
                    "selected_numbers": selected_numbers,
                    "cards": base_cards + supplement_cards,
                    "overall_interpretation": interpretation,
                    "overall_interpretation_markdown": followup_markdown,
                    "is_followup": True,
                    "supplement_cards": supplement_cards,
                }
            )
        except Exception as e:
            logger.error("追问补充抽牌流程失败: %s", str(e))
            yield event.plain_result(f"追问补充抽牌失败: {str(e)}")

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

        yield event.plain_result(
            "同一问题建议不要重复抽牌。\n"
            "- 深挖当前结果：/追问 你的问题\n"
            "- 系统会提示你从剩余牌中补抽 1-2 张说明牌\n"
            "- 若是全新问题，再重新发起 /tarot"
        )

        self.followup_sessions[session["session_key"]] = {
            "created_at": time.time(),
            "session_key": session["session_key"],
            "question": question,
            "theme": theme,
            "formation_name": formation_name,
            "selected_numbers": selected_numbers,
            "cards": record_cards,
            "remaining_cards": [
                {"number": idx, "card": card}
                for idx, card in enumerate(session.get("draw_pool", []), start=1)
                if idx not in set(selected_numbers)
            ],
            "latest_interpretation": interpretation,
            "followups": [],
            "supplement_cards": [],
        }

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

@register("divination", "Elysium-Seeker", "赛博占卜插件", "1.0.1")
class DivinationPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.tarot = Tarot(context, config)

    def _help_message(self) -> str:
        return (
            "赛博占卜 v1.0.1\n"
            "[/tarot 问题] 进入多牌占卜流程，先洗牌选阵，再输入编号抽牌\n"
            "[/tarot] 不带问题时会引导你先提问\n"
            "[主题选择] 默认强制使用 BilibiliTarot（可通过 force_theme 配置）\n"
            "[抽牌池默认规则] 默认展示该主题下全部可抽牌编号\n"
            "[编号规则] 编号从 1 开始，不存在 0 号牌\n"
            "[抽牌池配置] full_draw_pool=true 时始终全牌池\n"
            "[分析输出] 整体解读将渲染为 Markdown 风格占卜卡片\n"
            "[字体策略] 默认内置 Noto 中文字体，可设置 markdown_card_font_path 覆盖\n"
            "[核心原则] 同一问题不重复抽牌，先追问再考虑重抽\n"
            "[/追问 问题] 发起同题追问，系统会提示你从剩余牌中补抽 1-2 张说明牌\n"
            "[/追问 编号1 编号2 ...] 按追问提示选择说明牌编号\n"
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
                same_question_hint = self.tarot.get_same_question_redraw_hint(event, user_text)
                if same_question_hint:
                    yield event.plain_result(same_question_hint)
                    event.stop_event()
                    return
                async for result in self.tarot.divine(event, user_text):
                    yield result
            event.stop_event()
        except Exception as e:
            logger.error(f"处理 /tarot 命令失败: {str(e)}")
            yield event.plain_result(f"/tarot 命令执行失败: {str(e)}")

    @command("塔罗牌")
    async def onetime_divine_handler(self, event: AstrMessageEvent, text: str = ""):
        try:
            user_text = (text or "").strip()
            if user_text in {"帮助", "help", "Help", "HELP"}:
                yield event.plain_result(self._help_message())
            else:
                same_question_hint = self.tarot.get_same_question_redraw_hint(event, user_text)
                if same_question_hint:
                    yield event.plain_result(same_question_hint)
                    event.stop_event()
                    return
                async for result in self.tarot.onetime_divine(event, user_text):
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

    @command("追问")
    async def followup_handler(self, event: AstrMessageEvent, text: str = ""):
        try:
            followup_text = (text or "").strip()
            if not followup_text:
                yield event.plain_result("请输入追问内容。示例：/追问 我接下来三个月该怎么做？")
            elif self._is_draw_numbers_message(followup_text):
                if self.tarot.has_pending_followup_draw(event):
                    async for result in self.tarot.draw_followup_by_numbers(event, followup_text):
                        yield result
                else:
                    yield event.plain_result("当前没有待选择说明牌的追问，请先发送 /追问 你的问题。")
            else:
                async for result in self.tarot.followup(event, followup_text):
                    yield result
            event.stop_event()
        except Exception as e:
            logger.error("处理追问命令失败: %s", str(e))
            yield event.plain_result(f"追问命令执行失败: {str(e)}")

    @filter.regex(r"^\s*\d+(?:[\s,，]+\d+)*\s*$")
    async def draw_by_reply_handler(self, event: AstrMessageEvent, text: str = ""):
        try:
            if self.tarot.has_pending_session(event):
                message_text = self._extract_message_text(event, text)
                if not message_text:
                    return
                async for result in self.tarot.draw_by_numbers(event, message_text):
                    yield result
                event.stop_event()
                return

            if self.tarot.has_pending_followup_draw(event):
                message_text = self._extract_message_text(event, text)
                if not message_text:
                    return
                async for result in self.tarot.draw_followup_by_numbers(event, message_text):
                    yield result
                event.stop_event()
                return
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