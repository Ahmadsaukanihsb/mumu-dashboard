with open('templates/index.html', 'rb') as f:
    raw = f.read()

# Find the gift by value section
marker = b'Gift by Value'
idx = raw.find(marker)
if idx >= 0:
    section = raw[idx:idx+1200]
    print(repr(section[-300:]))
    print('---')
    # Check for encoding issues
    try:
        text = section.decode('utf-8')
        print('UTF-8 OK')
    except:
        print('UTF-8 DECODE FAILED')
        # find problematic bytes
        for i, b in enumerate(section):
            try:
                section[i:i+1].decode('utf-8')
            except:
                print(f'Bad byte at offset {i}: {hex(b)}')
