<div align="center">

# Tarot

_🔮 赛博塔罗牌 🔮_

</div>

## 序

_“许多傻瓜对千奇百怪的迷信说法深信不疑：象牙、护身符、黑猫、打翻的盐罐、驱邪、占卜、符咒、毒眼、塔罗牌、星象、水晶球、咖啡渣、手相、预兆、预言还有星座。”——《人类愚蠢辞典》_

## 关于

一个基于 AstrBot 框架的塔罗牌占卜插件，支持多牌阵和单张牌占卜，并通过 AI 生成详细解析。

## 版本

🧰 [v0.2.7](https://github.com/Elysium-Seeker/astrbot_plugin_tarot/releases/tag/v0.2.7)

⚠ 适配astrbot v3.4.39

👉 [如何添加新的塔罗牌主题资源？](./How-to-add-new-tarot-theme.md)欢迎贡献！🙏
👉 [塔罗插件工作流（当前版本）](./Tarot-Workflow.md)

## 安装

暂时需要下载自行放入插件目录。

由于插件只采用读取本地资源的方式。

自行下载塔罗资源，并在配置文件中配置资源地址。

[塔罗资源下载](https://www.123912.com/s/UQZ8Vv-uOLav?) 提取码:omBT

## 命令

1. [/tarot 问题] 进入多牌占卜流程：静心引导 -> 洗牌切牌 -> 匹配牌阵 -> 用户输入编号抽牌 -> 单牌+整体解读。

2. [/tarot] 若不带问题，插件会引导你先提问。

3. [塔罗牌 问题] 进入单张抽牌流程，并提供单牌+整体解读。

4. [抽牌 编号1 编号2 ...] 根据提示输入编号完成抽牌与翻牌（默认全牌池，受 full_draw_pool 控制）。

5. [自动抽牌] 当存在待抽牌会话时，可直接回复编号（如 1 5 9）继续流程。

6. [占卜记录 数量] 查看你的最近占卜记录（默认 3 条，最多 10 条）。

7. [开启/关闭群聊转发] 切换群聊转发模式。

## 资源说明

1. 韦特塔罗(Waite Tarot)包括22张大阿卡纳(Major Arcana)牌与权杖(Wands)、星币(Pentacles)、圣杯(Cups)、宝剑(Swords)各系14张的小阿卡纳(Minor Arcana)共56张牌组成，其中国王、皇后、骑士、侍从也称为宫廷牌(Court Cards)；

   - BilibiliTarot：B站幻星集主题塔罗牌
   - TouhouTarot：东方主题塔罗牌，仅包含大阿卡纳

   ⚠ 资源中额外四张王牌(Ace)不在体系中，因此不会在占卜时用到，因为小阿卡纳中各系均有Ace牌，但可以自行收藏。

2. `tarot.json`中对牌阵，抽牌张数、是否有切牌、各牌正逆位解读进行说明。`cards` 字段下对所有塔罗牌做了正逆位含义与资源路径的说明；

3. 根据牌阵的不同有不同的塔罗牌解读，同时也与问卜者的问题、占卜者的解读等因素相关，因此不存在所谓的解读方式正确与否。`cards` 字段下的正逆位含义参考以下以及其他网络资源：

   - 《棱镜/耀光塔罗牌中文翻译》，中华塔罗会馆(CNTAROT)，版权原因恕不提供
   - [AlerHugu3s/PluginVoodoo](https://github.com/AlerHugu3s/PluginVoodoo/blob/master/data/PluginVoodoo/TarotData/Tarots.json)
   - [塔罗.中国](https://tarotchina.net/)
   - [塔罗牌](http://www.taluo.org/)
   - [灵匣](https://www.lnka.cn/)

   🤔 也可以说是原作者MinatoAquaCrews的解读版本

## 本插件改自

1. [真寻bot插件库/tarot](https://github.com/AkashiCoin/nonebot_plugins_zhenxun_bot)

2. [haha114514/tarot_hoshino](https://github.com/haha114514/tarot_hoshino)

3.  [hMinatoAquaCrews/nonebot_plugin_tarot](https://github.com/MinatoAquaCrews/nonebot_plugin_tarot)
