import re
from collections import Counter

with open('templates/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

ids = re.findall(r'id="(\w+)"', content)
dupes = {k: v for k, v in Counter(ids).items() if v > 1}
print('Duplicate IDs:', dupes if dupes else 'None')
print('harvestSelectedCount count:', content.count('harvestSelectedCount'))
print('harvestFruitsResult count:', content.count('harvestFruitsResult'))
print('harvestTotalCount count:', content.count('harvestTotalCount'))
print('harvestTotalValue count:', content.count('harvestTotalValue'))
