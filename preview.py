import asyncio
from playwright.async_api import async_playwright
import markdown
import os

async def render_preview():
    md_text = """# 塔罗占卜分析卡
## 问题
- 我近期的工作运势如何？
## 牌阵
- 圣三角（过去、现在、未来）
## 牌面概览
- 过去：愚者正位 · 新的开始、冒险
- 现在：魔术师逆位 · 缺乏动力、技能不足
- 未来：命运之轮正位 · 转机、好运
---
## 深度解读
过去的你对待工作充满了**好奇与冒险精神**，像愚者一样不拘一格，可能刚开启了一段新的旅程。
然而现在似乎遇到了瓶颈，面临着动力不足或技能需要提升的状况。请不要灰心，未来的**转机**即将到来，命运之轮会为你开启新的篇章。

### 行动建议
1. **保持乐观心态**：不要被眼前的困难打倒。
2. **精进专业技能**：弥补魔术师逆位带来的不足。
3. **迎接顺其自然的变化**：顺应命运之轮的转动。
"""
    html_content = markdown.markdown(md_text)
    html = f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Ma+Shan+Zheng&family=Noto+Serif+SC:wght@400;700;900&display=swap');
            
            :root {{
                --gold-light: #f9df9f;
                --gold-mid: #d4af37;
                --gold-dark: #8c6d23;
                --bg-deep: #0a0a0f;
                --bg-card: #15111e;
                --text-main: #dfd5c5;
            }}

            body {{
                font-family: "Noto Serif SC", "Microsoft YaHei", serif;
                background-color: var(--bg-deep);
                background-image: 
                    radial-gradient(circle at 15% 50%, rgba(73, 50, 99, 0.15), transparent 50%),
                    radial-gradient(circle at 85% 30%, rgba(30, 80, 120, 0.15), transparent 50%);
                color: var(--text-main);
                padding: 60px;
                margin: 0;
                width: 800px;
                display: flex;
                justify-content: center;
            }}

            .tarot-card {{
                width: 100%;
                position: relative;
                background: linear-gradient(180deg, #181425 0%, #0d0a14 100%);
                border-radius: 16px;
                padding: 12px;
                box-shadow: 
                    0 20px 50px rgba(0,0,0,0.8),
                    0 0 0 1px rgba(212, 175, 55, 0.2),
                    inset 0 0 20px rgba(0,0,0,1);
            }}

            .tarot-inner {{
                position: relative;
                border: 2px solid transparent;
                border-image: linear-gradient(45deg, var(--gold-dark), var(--gold-light), var(--gold-dark)) 1;
                padding: 50px 60px;
                background: 
                    linear-gradient(rgba(21, 17, 30, 0.95), rgba(21, 17, 30, 0.95)),
                    url('data:image/svg+xml;utf8,<svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg"><path d="M50 0L50 100M0 50L100 50M25 25L75 75M25 75L75 25" stroke="rgba(212,175,55,0.03)" stroke-width="1"/></svg>');
            }}

            .corner {{
                position: absolute;
                width: 40px;
                height: 40px;
                border: 2px solid var(--gold-mid);
                opacity: 0.8;
            }}
            .corner-tl {{ top: -2px; left: -2px; border-right: none; border-bottom: none; }}
            .corner-tr {{ top: -2px; right: -2px; border-left: none; border-bottom: none; }}
            .corner-bl {{ bottom: -2px; left: -2px; border-right: none; border-top: none; }}
            .corner-br {{ bottom: -2px; right: -2px; border-left: none; border-top: none; }}
            
            .corner::after {{
                content: '';
                position: absolute;
                width: 8px; height: 8px;
                background: var(--gold-mid);
                border-radius: 50%;
            }}
            .corner-tl::after {{ top: 4px; left: 4px; }}
            .corner-tr::after {{ top: 4px; right: 4px; }}
            .corner-bl::after {{ bottom: 4px; left: 4px; }}
            .corner-br::after {{ bottom: 4px; right: 4px; }}

            .emblem {{
                text-align: center;
                margin-bottom: 20px;
                position: relative;
                z-index: 2;
            }}
            .emblem svg {{
                width: 80px;
                height: 80px;
                fill: none;
                stroke: var(--gold-mid);
                stroke-width: 1.5;
                filter: drop-shadow(0 0 8px rgba(212,175,55,0.4));
            }}

            h1 {{
                font-family: "Ma Shan Zheng", "Noto Serif SC", serif;
                text-align: center;
                font-size: 48px;
                font-weight: 400;
                margin: 0 0 35px 0;
                padding-bottom: 30px;
                color: transparent;
                background: linear-gradient(to right, var(--gold-dark), var(--gold-light), var(--gold-light), var(--gold-dark));
                -webkit-background-clip: text;
                background-clip: text;
                letter-spacing: 8px;
                text-shadow: 0 4px 10px rgba(0,0,0,0.5);
                position: relative;
                z-index: 2;
            }}
            
            h1::after {{
                content: '✧ ✦ ✧';
                position: absolute;
                bottom: -5px;
                left: 50%;
                transform: translateX(-50%);
                font-size: 18px;
                color: var(--gold-dark);
                letter-spacing: 16px;
                text-shadow: none;
            }}

            h2 {{
                color: var(--gold-light);
                font-size: 26px;
                font-weight: 700;
                margin-top: 45px;
                margin-bottom: 20px;
                display: flex;
                align-items: center;
                gap: 15px;
                letter-spacing: 2px;
            }}
            h2::before, h2::after {{
                content: '';
                flex: 1;
                height: 1px;
                background: linear-gradient(to right, transparent, var(--gold-dark), transparent);
            }}

            h3 {{
                color: var(--gold-mid);
                font-size: 20px;
                margin-top: 30px;
                margin-bottom: 15px;
            }}

            ul {{
                list-style: none;
                padding-left: 10px;
                margin: 0;
            }}
            li {{
                margin-bottom: 16px;
                line-height: 1.9;
                font-size: 18px;
                position: relative;
                padding-left: 32px;
            }}
            li::before {{
                content: '✩';
                position: absolute;
                left: 0;
                top: 0px;
                color: var(--gold-mid);
                font-size: 22px;
                text-shadow: 0 0 8px rgba(212,175,55,0.6);
            }}

            strong {{
                color: var(--gold-light);
                font-weight: 700;
                background: rgba(212, 175, 55, 0.1);
                padding: 2px 6px;
                border-radius: 4px;
                border-bottom: 1px solid rgba(212, 175, 55, 0.4);
            }}

            hr {{
                border: none;
                height: 1px;
                background: linear-gradient(to right, transparent, var(--gold-dark), transparent);
                margin: 50px 0;
                position: relative;
                overflow: visible;
            }}
            hr::after {{
                content: '♦';
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background: var(--bg-card);
                padding: 0 20px;
                color: var(--gold-light);
                font-size: 22px;
                text-shadow: 0 0 10px rgba(212,175,55,0.5);
            }}

            p {{
                line-height: 2.1;
                font-size: 18px;
                text-align: justify;
                margin-bottom: 20px;
            }}
            
            p:not(:first-of-type) {{
                text-indent: 2em;
            }}

            .glow {{
                position: absolute;
                top: 5%;
                left: 50%;
                transform: translateX(-50%);
                width: 400px;
                height: 400px;
                background: radial-gradient(circle, rgba(212,175,55,0.06) 0%, transparent 70%);
                pointer-events: none;
                z-index: 1;
            }}
            
            .content {{
                position: relative;
                z-index: 2;
            }}
        </style>
    </head>
    <body id="body">
        <div class="tarot-card" id="card">
            <div class="glow"></div>
            <div class="tarot-inner">
                <div class="corner corner-tl"></div>
                <div class="corner corner-tr"></div>
                <div class="corner corner-bl"></div>
                <div class="corner corner-br"></div>
                
                <div class="emblem">
                    <svg viewBox="0 0 100 100">
                        <circle cx="50" cy="50" r="45" stroke-dasharray="2 6" stroke-linecap="round" />
                        <circle cx="50" cy="50" r="38"/>
                        <circle cx="50" cy="50" r="30" stroke-dasharray="1 4"/>
                        <path d="M50 12 L50 88 M12 50 L88 50 M23 23 L77 77 M23 77 L77 23" stroke-width="0.5" opacity="0.6"/>
                        <path d="M50 22 A28 28 0 0 1 78 50 A28 28 0 0 1 50 78 A28 28 0 0 1 22 50 A28 28 0 0 1 50 22" fill="rgba(212,175,55,0.1)"/>
                        <circle cx="50" cy="50" r="6" fill="var(--gold-mid)"/>
                        <path d="M50 5 L55 15 L50 25 L45 15 Z" fill="var(--gold-light)" stroke="none"/>
                        <path d="M50 75 L55 85 L50 95 L45 85 Z" fill="var(--gold-light)" stroke="none"/>
                        <path d="M5 50 L15 45 L25 50 L15 55 Z" fill="var(--gold-light)" stroke="none"/>
                        <path d="M75 50 L85 45 L95 50 L85 55 Z" fill="var(--gold-light)" stroke="none"/>
                    </svg>
                </div>
                
                <div class="content">
                    {html_content}
                </div>
            </div>
        </div>
    </body>
    </html>
    '''
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html, wait_until='networkidle')
        await page.evaluate('document.fonts.ready')
        
        card_element = await page.query_selector('.tarot-card')
        if card_element:
            await card_element.screenshot(path='preview.png')
        else:
            await page.screenshot(path='preview.png', full_page=True)
        await browser.close()
        print("PREVIEW_GENERATED")

if __name__ == "__main__":
    asyncio.run(render_preview())
