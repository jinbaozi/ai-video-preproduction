"""Render a deliberately flat composition guide from the frozen café layout."""
from pathlib import Path
from PIL import Image, ImageDraw

W, H = 1672, 941
im = Image.new('RGB', (W, H), '#d8d4cc')
d = ImageDraw.Draw(im)

def xy(x, y):
    return round(x * W), round(y * H)

def rect(a, b, color):
    d.rectangle((*xy(*a), *xy(*b)), fill=color)

# Background and camera-space furniture are layout shapes, never appearance masters.
rect((0, 0), (.13, .68), '#dbe9ea')
rect((.055, 0), (.07, .68), '#52646b')
rect((.42, .02), (.60, .23), '#9d998f')
rect((.435, .035), (.585, .215), '#c6c4bd')
rect((.01, .55), (.20, 1), '#86654c')
rect((.79, .55), (.99, 1), '#86654c')

# Left and right seated adults; silhouettes specify presence and reach only.
d.ellipse((*xy(.17, .11), *xy(.35, .47)), fill='#d3aa8e')
d.polygon([xy(.10, .36), xy(.35, .36), xy(.43, .76), xy(.055, .76)], fill='#273c57')
d.ellipse((*xy(.66, .11), *xy(.84, .47)), fill='#d3aa8e')
d.polygon([xy(.64, .38), xy(.91, .38), xy(.95, .77), xy(.60, .77)], fill='#c2b29b')
d.line([xy(.32, .58), xy(.34, .67), xy(.375, .715)], fill='#d3aa8e', width=42)
d.line([xy(.74, .58), xy(.70, .69), xy(.64, .755)], fill='#d3aa8e', width=36)

# Back and front of the lower tabletop follow the preregistered camera-space lines.
d.polygon([xy(.21, .775), xy(.80, .775), xy(.91, .897), xy(.09, .897)], fill='#9a6d44')
d.line([xy(.21, .775), xy(.80, .775)], fill='#4a3020', width=7)
d.line([xy(.09, .897), xy(.91, .897)], fill='#4a3020', width=9)

# The envelope's visual center is exactly the frozen target (0.378362, 0.716245).
cx, cy = .37836213115936546, .7162451001611281
d.polygon([xy(cx-.05, cy-.012), xy(cx+.05, cy-.012),
           xy(cx+.05, cy+.012), xy(cx-.05, cy+.012)], fill='#243d66')

out = Path(__file__).resolve().parent / 'guide.png'
im.save(out, optimize=True)
print(out)
