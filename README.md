<div align="center">

# Tarot

_🔮 赛博塔罗牌 🔮_

</div>

## 核心特性

- `/tarot 问题` 多牌占卜（提问 -> 选阵 -> 编号抽牌 -> 单牌+整体解读）。
- `塔罗牌 问题` 单张占卜。
- 默认强制主题为 `BilibiliTarot`（可通过 `force_theme` 配置修改，留空则随机）。
- 支持三种抽牌输入：直回编号、`抽牌 ...`、`/tarot 编号...` 兜底。
- 整体解读输出为 Markdown 风格占卜分析卡片（参考 pillowmd 样式）。
- 默认全牌池抽牌（`full_draw_pool=true`）。
- 支持占卜记录查询与群聊转发开关。

## 版本

- 版本： [v0.2.12](https://github.com/Elysium-Seeker/astrbot_plugin_tarot/releases/tag/v0.2.12)
- 适配：AstrBot v3.4.39

## 安装

1. 将插件放入 AstrBot 插件目录。
2. 当前仓库已内置 TouhouTarot 与 BilibiliTarot 资源，可直接使用。
3. 若使用外部资源目录，在插件配置中设置 `resource_path`。
4. 若需切回随机主题，将 `force_theme` 设为空字符串。

外部资源下载（可选）： [塔罗资源下载](https://www.123912.com/s/UQZ8Vv-uOLav?)（提取码：`omBT`）

## 指令速查

1. `/tarot 问题`：发起多牌占卜。
2. `/tarot`：不带问题时返回提问引导。
3. `塔罗牌 问题`：发起单张占卜。
4. `抽牌 编号1 编号2 ...`：按提示抽牌（编号从 1 开始，不存在 0 号牌）。
5. 直接回复编号（如 `1 5 9`）：有待抽牌会话时自动抽牌。
6. `/tarot 1 5 9`：纯数字被分流时的命令兜底。
7. `占卜记录 数量`：查看最近记录（默认 3，最多 10）。
8. `开启群聊转发` / `关闭群聊转发`：切换群聊发送模式。

## 文档

- [塔罗插件工作流（当前版本）](./Tarot-Workflow.md)
- [如何添加新的塔罗牌主题资源？](./How-to-add-new-tarot-theme.md)
