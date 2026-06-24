import re

with open(r'C:\Users\Jin\Desktop\jinbet_update\jinbet_update\index.html', encoding='utf-8') as f:
    content = f.read()

# Find all "胜其他"/"平其他"/"负其他" in the whole file
all_others = re.findall(r'"(胜其他|平其他|负其他)": "([^"]+)"', content)
from collections import Counter
counts = Counter(k for k, v in all_others)
print("All occurrences:")
for k, v in counts.items():
    print(f"  {k}: {v} times")

# Find the injected localStorage section (look for SCHEDULE or localStorage.setItem)
# The injected data starts after the SCHEDULE definition
idx = content.find("localStorage.setItem('worldcup_odds_v737'")
if idx > 0:
    injected = content[idx:]
    injected_others = re.findall(r'"(胜其他|平其他|负其他)": "([^"]+)"', injected)
    inj_counts = Counter(k for k, v in injected_others)
    print("\nIn injected data:")
    for k, v in inj_counts.items():
        print(f"  {k}: {v} times")
else:
    print("Could not find injected data section")
