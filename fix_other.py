import re

with open(r'C:\Users\Jin\Desktop\jinbet_update\jinbet_update\index.html', encoding='utf-8') as f:
    content = f.read()

# Remove all '其他' blocks in the injected data section
# Pattern matches the block followed by newline+indent
pattern = r'    "其他": \{\n      "胜其他": "[^"]*",\n      "平其他": "[^"]*",\n      "负其他": "[^"]*"\n    \},\n'

matches = re.findall(pattern, content)
print(f'Found {len(matches)} 胜/平/负其他 blocks to remove')

new_content = re.sub(pattern, '', content)

with open(r'C:\Users\Jin\Desktop\jinbet_update\jinbet_update\index.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Done! Removed "其他" blocks from injected data')
