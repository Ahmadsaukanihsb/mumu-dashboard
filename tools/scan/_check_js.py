import re

with open('static/script.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find all textContent assignments
for i, line in enumerate(lines, 1):
    if 'textContent' in line and '=' in line:
        # Extract element ID
        match = re.search(r"getElementById\('(\w+)'\)", line)
        if match:
            print(f"Line {i}: {match.group(1)} - {line.strip()[:80]}")
