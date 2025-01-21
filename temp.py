import re

# Your markdown content
markdown_content = """
# Topic A
## Subtopic A.1
- Point 1
- Point 2

# Topic B
## Subtopic B.1
- Point 1
## Subtopic B.2
- Point 1
![image](link)
"""

# Define the regex pattern to match top-level headers
pattern = r'(?m)^# .*$'

# Find all matches for top-level headers
matches = list(re.finditer(pattern, markdown_content))

# Initialize a list to hold the split sections
sections = []

# Iterate over the matches to extract sections
for i in range(len(matches)):
    start = matches[i].start()
    end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown_content)
    sections.append(markdown_content[start:end].strip())

# Output the split sections
for section in sections:
    print(section)
    print("-" * 20)
