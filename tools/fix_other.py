import re
import os

# 路径自动定位：脚本位于 tools/，目标文件在上级目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_HTML = os.path.join(BASE_DIR, 'index.html')

with open(INDEX_HTML, encoding='utf-8') as f:
    content = f.read()

# Remove all '其他' blocks in the injected data section
# Pattern matches the block followed by newline+indent
pattern = r'    "其他": \{\n      "胜其他": "[^"]*",\n      "平其他": "[^"]*",\n      "负其他": "[^"]*"\n    \},\n'

matches = re.findall(pattern, content)
print(f'Found {len(matches)} 胜/平/负其他 blocks to remove')

new_content = re.sub(pattern, '', content)

with open(INDEX_HTML, 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Done! Removed "其他" blocks from injected data')
