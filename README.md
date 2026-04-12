<div align="center">

# Tarot

_🔮 赛博塔罗牌 🔮_

</div>

## 序

_“许多傻瓜对千奇百怪的迷信说法深信不疑：象牙、护身符、黑猫、打翻的盐罐、驱邪、占卜、符咒、毒眼、塔罗牌、星象、水晶球、咖啡渣、手相、预兆、预言还有星座。”——《人类愚蠢辞典》_

## 关于

一个基于 AstrBot 框架的塔罗牌占卜插件，支持多牌阵和单张牌占卜，并通过 AI 生成整体解析，最终渲染为 Markdown 风格占卜分析卡片。

## 版本

- 版本： [v0.2.24](https://github.com/Elysium-Seeker/astrbot_plugin_tarot/releases/tag/v0.2.24)

## 更新日志
- **v0.2.24**: 重构追问系统：同题默认不重抽；`追问` 专注深挖原牌；新增 `补牌` 命令可针对某张牌补抽 1-2 张说明牌。
- **v0.2.23**: 新增 `追问` 命令，可基于最近一轮占卜继续提问；支持 `followup_expire_seconds` 配置追问上下文时效。
- **v0.2.22**: 插件内置 Noto 中文字体文件，Markdown 卡片优先使用内置字体渲染，避免中文方框占位符。
- **v0.2.21**: 修复 Markdown 卡片中文“方框占位符”问题：扩展中文字体探测路径；无可用中文字体时自动回退纯文本。
- **v0.2.20**: Markdown 分析卡片改为 Pillow 本地渲染，不再依赖浏览器内核；新增 `markdown_card_font_path` 配置项。
- **v0.2.19**: 修复 Playwright 缺少浏览器内核时的崩溃，自动回退纯文本分析；增强 Linux/容器兼容启动参数。
- **v0.2.18**: 修复 `_normalize_markdown_text` 导致的抽牌崩溃，清理多余重复代码。
- **v0.2.17**: 重写 Markdown 渲染 UI，启用神秘主义暗黑星空风格排版，使用 Playwright 捕获页面截图。

⚠ 适配 AstrBot v3.4.39

👉 [如何添加新的塔罗牌主题资源？](./How-to-add-new-tarot-theme.md) 欢迎贡献！
👉 [塔罗插件工作流（当前版本）](./Tarot-Workflow.md)

## 安装

1. 将插件放入 AstrBot 插件目录。
2. 当前仓库已内置 TouhouTarot 与 BilibiliTarot 资源，可直接使用。
3. 若使用外部资源目录，在插件配置中设置 `resource_path`。
4. 默认强制主题为 `BilibiliTarot`；若需随机主题，将 `force_theme` 设为空字符串。
5. 本插件使用 Pillow 进行 Markdown 分析卡片渲染，不依赖浏览器内核。
6. 插件已内置 Noto 中文字体（位于 `resources/fonts`），默认可直接渲染中文卡片。
7. 若需覆盖默认字体，可设置 `markdown_card_font_path` 指向本机 ttf/ttc 字体文件或字体目录。
8. 若需调整追问有效时间，可设置 `followup_expire_seconds`（默认 1800 秒）。
9. 若不需要卡片渲染，可将 `enable_markdown_card` 设为 `false` 回退纯文本分析。

## 追问宗旨

1. 同一个问题，不重复抽牌。
2. 对结果不满意时，优先追问深挖，而不是反复重抽。
3. 若是全新问题或情境实质变化，再重新发起占卜。

外部资源下载（可选）： [塔罗资源下载](https://www.123912.com/s/UQZ8Vv-uOLav?)（提取码：`omBT`）

## 命令

1. [/tarot 问题] 进入多牌占卜流程：静心引导 -> 洗牌切牌 -> 匹配牌阵 -> 用户输入编号抽牌 -> 展示牌面 -> Markdown 风格整体分析卡片（默认使用内置 Noto 字体渲染中文）。

2. [/tarot] 若不带问题，插件会引导你先提问。

3. [塔罗牌 问题] 进入单张抽牌流程，并返回 Markdown 风格整体分析卡片。

4. [抽牌 编号1 编号2 ...] 根据提示输入编号完成抽牌与翻牌（编号从 1 开始，不存在 0 号牌）。

5. [自动抽牌] 当存在待抽牌会话时，可直接回复编号（如 1 5 9）继续流程。

6. [命令兜底] 若平台将纯数字消息分流到主对话，可使用 [/tarot 1 5 9] 直接进入抽牌。

7. [占卜记录 数量] 查看你的最近占卜记录（默认 3 条，最多 10 条）。

8. [开启/关闭群聊转发] 切换群聊转发模式。

9. [force_theme 配置] 默认 `BilibiliTarot`，可改为其他主题目录名；留空则随机主题。

10. [追问 问题] 基于最近一轮占卜继续深挖（不新增抽牌）。

11. [补牌 牌位编号 1或2 追问内容] 针对某张牌从剩余牌中补抽 1-2 张说明牌（如：`/补牌 2 1 这张牌想告诉我什么更深信息？`）。


## 资源说明

1. 韦特塔罗(Waite Tarot)包括22张大阿卡纳(Major Arcana)牌与权杖(Wands)、星币(Pentacles)、圣杯(Cups)、宝剑(Swords)各系14张的小阿卡纳(Minor Arcana)共56张牌组成，其中国王、皇后、骑士、侍从也称为宫廷牌(Court Cards)。

	- BilibiliTarot：B站幻星集主题塔罗牌（当前默认强制主题）
	- TouhouTarot：东方主题塔罗牌，仅包含大阿卡纳

	⚠ 资源中额外四张王牌(Ace)不在体系中，因此不会在占卜时用到，因为小阿卡纳中各系均有 Ace 牌，但可以自行收藏。

2. `tarot.json` 对牌阵、抽牌张数、是否有切牌、各牌正逆位含义进行说明；`cards` 字段包含塔罗牌含义与资源路径。

3. 根据牌阵不同会有不同解读，同时与问卜者问题相关，不存在唯一“标准答案”。`cards` 字段下正逆位含义参考以下资源：

	- 《棱镜/耀光塔罗牌中文翻译》，中华塔罗会馆(CNTAROT)，版权原因恕不提供
	- [AlerHugu3s/PluginVoodoo](https://github.com/AlerHugu3s/PluginVoodoo/blob/master/data/PluginVoodoo/TarotData/Tarots.json)
	- [塔罗.中国](https://tarotchina.net/)
	- [塔罗牌](http://www.taluo.org/)
	- [灵匣](https://www.lnka.cn/)

## 本插件改自

1. [真寻bot插件库/tarot](https://github.com/AkashiCoin/nonebot_plugins_zhenxun_bot)

2. [haha114514/tarot_hoshino](https://github.com/haha114514/tarot_hoshino)

3. [hMinatoAquaCrews/nonebot_plugin_tarot](https://github.com/MinatoAquaCrews/nonebot_plugin_tarot)

## 文档

- [塔罗插件工作流（当前版本）](./Tarot-Workflow.md)
- [如何添加新的塔罗牌主题资源？](./How-to-add-new-tarot-theme.md)
