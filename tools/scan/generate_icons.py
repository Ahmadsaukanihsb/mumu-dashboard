"""Generate PWA icons for Dashboard Roblox"""
import os
import math

def create_icon(size, output_path):
    """Create a simple SVG icon and save as HTML for manual conversion"""
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#ff3b4a"/>
      <stop offset="100%" style="stop-color:#dc2f3b"/>
    </linearGradient>
  </defs>
  <rect width="{size}" height="{size}" rx="{size//8}" fill="url(#bg)"/>
  <text x="50%" y="55%" dominant-baseline="middle" text-anchor="middle" fill="white" font-family="Arial, sans-serif" font-size="{size//3}" font-weight="bold">R</text>
  <circle cx="{size*0.75}" cy="{size*0.25}" r="{size//10}" fill="#22c55e"/>
</svg>'''
    
    with open(output_path, 'w') as f:
        f.write(svg_content)
    return output_path

def main():
    icons_dir = os.path.join(os.path.dirname(__file__), 'static', 'icons')
    os.makedirs(icons_dir, exist_ok=True)
    
    sizes = [72, 96, 128, 144, 152, 192, 384, 512]
    
    for size in sizes:
        # Regular icon
        path = os.path.join(icons_dir, f'icon-{size}x{size}.svg')
        create_icon(size, path)
        print(f'Created: {path}')
        
        # Maskable icon (same for now)
        maskable_path = os.path.join(icons_dir, f'icon-{size}x{size}-maskable.svg')
        create_icon(size, maskable_path)
        print(f'Created: {maskable_path}')
    
    print('\nNote: Convert SVG files to PNG using online converter or ImageMagick:')
    print('  for f in static/icons/*.svg; do convert "$f" "${f%.svg}.png"; done')

if __name__ == '__main__':
    main()
