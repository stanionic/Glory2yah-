"""Fix: the annotation canvas must stay VISIBLE while a media is on screen.

Participants never draw (penActive stays False for them) but they must SEE the
teacher's live strokes, so display is driven by "is there a media?", while
pointer-events keep the canvas transparent to mouse/touch for non-drawers.
"""
import io

PATH = 'templates/konferans/room.html'

OLD = ("        resizeAnnotationCanvas();\r\n"
       "        canvas.style.display = penActive ? 'block' : 'none';\r\n"
       "        canvas.style.pointerEvents = penActive ? 'auto' : 'none';")

NEW = ("        resizeAnnotationCanvas();\r\n"
       "        // Always visible while a media is on screen: participants must SEE the\r\n"
       "        // teacher live strokes even though they cannot draw themselves.\r\n"
       "        canvas.style.display = 'block';\r\n"
       "        canvas.style.pointerEvents = penActive ? 'auto' : 'none';")

text = io.open(PATH, encoding='utf-8', newline='').read()
count = text.count(OLD)
assert count == 1, 'anchor found %d times (expected 1)' % count
io.open(PATH, 'w', encoding='utf-8', newline='').write(text.replace(OLD, NEW))
print('syncMediaPenLayer canvas visibility patched (1 occurrence)')
