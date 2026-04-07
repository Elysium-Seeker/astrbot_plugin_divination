import re

with open('main.py', 'r', encoding='utf-8') as f:
    main_code = f.read()

new_html = r'''
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
'''

main_code = re.sub(r'            html = f\"\"\"[\s\S]*?</html>\n            \"\"\"', new_html.strip(), main_code)

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(main_code)

with open('metadata.yaml', 'r', encoding='utf-8') as f:
    meta = f.read()

meta = meta.replace('0.2.15', '0.2.16')
with open('metadata.yaml', 'w', encoding='utf-8') as f:
    f.write(meta)

with open('README.md', 'r', encoding='utf-8') as f:
    readme = f.read()
readme = readme.replace('v0.2.15', 'v0.2.16')
with open('README.md', 'w', encoding='utf-8') as f:
    f.write(readme)

print('MAIN_UPDATED')
