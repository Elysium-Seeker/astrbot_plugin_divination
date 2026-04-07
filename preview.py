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
    '''
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_content(html, wait_until='networkidle')
        await page.evaluate('document.fonts.ready')
        
        card_element = await page.query_selector('.card')
        if card_element:
            await card_element.screenshot(path='preview.png')
        else:
            await page.screenshot(path='preview.png', full_page=True)
        await browser.close()
        print("PREVIEW_GENERATED")

if __name__ == "__main__":
    asyncio.run(render_preview())
