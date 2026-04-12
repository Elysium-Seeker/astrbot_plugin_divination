<div align="center">

# AstrBot Plugin Divination

_🔮 赛博占卜 🔮_

<img src="https://count.getloli.com/@astrbot_plugin_divination?theme=booru-helltaker" alt="Moe Counter" />

<br>

![GitHub Release](https://img.shields.io/github/v/release/Elysium-Seeker/astrbot_plugin_divination?style=flat-square)
![GitHub License](https://img.shields.io/github/license/Elysium-Seeker/astrbot_plugin_divination?style=flat-square)

</div>

## 序

_“许多傻瓜对千奇百怪的迷信说法深信不疑：象牙、护身符、黑猫、打翻的盐罐、驱邪、占卜、符咒、毒眼、塔罗牌、星象、水晶球、咖啡渣、手相、预兆、预言还有星座。”——《人类愚蠢辞典》_

## 核心特性

- **多牌阵/单张占卜**：灵活的多牌阵工作流与快速单卡解读。
- **自定义视觉卡片**：自动生成排版精巧的 Markdown 分析长图，自带 Noto 中文字体防乱码。
- **深度追问**：解牌后可随时通过追问命令补抽说明牌，由 AI 进行连贯的深度解析。

## 更新日志

- **v1.0.0**：项目正式重命名为 `astrbot_plugin_divination` 进阶为综合占卜插件，极简说明更新。

## 安装

进入 AstrBot 的插件目录，克隆本仓库并安装依赖即可：

```bash
git clone https://github.com/Elysium-Seeker/astrbot_plugin_divination.git
cd astrbot_plugin_divination
pip install -r requirements.txt
```

重启 AstrBot 开始使用。

## 指令速查

| 指令 | 说明 |
| --- | --- |
| `/tarot [问题]` | 引导进入多牌阵流程。 |
| `/塔罗牌 [问题]` | 快速抽取一张塔罗牌。 |
| `/抽牌 [编号...]` | 输入数字编号进行翻牌（无 0 号）。 |
| `/追问 [问题]` | 对上一轮的结论进行追问，补抽说明牌来延展分析。 |
| `/占卜记录 [数量]` | 获取历史记录，如：`/占卜记录 3`。 |

