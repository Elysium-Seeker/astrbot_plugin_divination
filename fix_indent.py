with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if line.strip().startswith('html = f"""'):
        lines[i] = '            html = f"""\n'
        
with open('main.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
