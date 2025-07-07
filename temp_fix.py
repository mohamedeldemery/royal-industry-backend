import re

# Read employees.py
with open('routers/employees.py', 'r') as f:
    content = f.read()

# Replace the hardcoded DATABASE_URL and connection function
content = re.sub(
    r'DATABASE_URL = .*',
    'DATABASE_URL = os.getenv("DATABASE_URL")',
    content
)

# Write back
with open('routers/employees.py', 'w') as f:
    f.write(content)

print("Fixed employees.py database connection")
