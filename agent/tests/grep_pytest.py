import os

# Define the directory to search
directory = 'agent/tests'

# List to store results
results = []

# Iterate through all files in the directory
for root, dirs, files in os.walk(directory):
    for file in files:
        if file.endswith('.py'):
            file_path = os.path.join(root, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Check if 'pytest' is in the content
                    if 'pytest' in content:
                        # Find all line numbers where 'pytest' appears
                        lines = content.split('\n')
                        for i, line in enumerate(lines, 1):
                            if 'pytest' in line:
                                results.append(f"File: {file_path}\nLine {i}: {line.strip()}\n")
            except Exception as e:
                results.append(f"Error reading {file_path}: {e}\n")

# Output results
if results:
    print("--- Matches for 'pytest' in agent/tests ---")
    for result in results:
        print(result)
else:
    print("No matches found for 'pytest' in agent/tests.")