from PIL import Image
# Create a tiny 16x16 transparent image
img = Image.new('RGBA', (16, 16), (0, 0, 0, 0))
img.save('blank_icon.ico')
