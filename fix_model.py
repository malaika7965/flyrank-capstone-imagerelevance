import re

with open("vision_pipeline.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('model="gemini-2.0-flash"', 'model="gemini-3.8-flash"')

with open("vision_pipeline.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Model name updated to gemini-3.8-flash")
