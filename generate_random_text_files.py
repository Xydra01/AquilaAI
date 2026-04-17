import random
import string
from datetime import datetime

def generate_random_text(length=50):
    """Generate random text content"""
    letters = string.ascii_letters + string.digits + ' \n'
    return ''.join(random.choice(letters) for _ in range(length))

# Configuration
NUM_FILES = 1000
OUTPUT_DIR = "Agent-Creations/random_text_files"
MIN_LENGTH = 50
MAX_LENGTH = 200

# Create output directory if it doesn't exist
import os
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"Generating {NUM_FILES} random text files...")
print(f"Output directory: {OUTPUT_DIR}")
print("-" * 50)

for i in range(NUM_FILES):
    filename = f"random_text_{i+1:04d}.txt"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    # Generate random text with varying length
    length = random.randint(MIN_LENGTH, MAX_LENGTH)
    content = generate_random_text(length)
    
    # Write to file
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    
    if (i + 1) % 200 == 0:
        print(f"Progress: {i + 1}/{NUM_FILES} files created ({(i+1)/NUM_FILES*100:.1f}%)")

print("-" * 50)
print(f"✅ SUCCESS! Created {NUM_FILES} random text files in {OUTPUT_DIR}")
print(f"\nSample file (random_text_0001.txt):")
with open(os.path.join(OUTPUT_DIR, "random_text_0001.txt"), 'r') as f:
    print(f.read()[:200])

# Create a summary report
summary_path = os.path.join(OUTPUT_DIR, "generation_summary.txt")
with open(summary_path, 'w') as f:
    f.write("=" * 60 + "\n")
    f.write("RANDOM TEXT FILE GENERATION SUMMARY\n")
    f.write("=" * 60 + "\n\n")
    f.write(f"Total Files Created: {NUM_FILES}\n")
    f.write(f"Output Directory: {OUTPUT_DIR}\n")
    f.write(f"Date Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    f.write("File Naming Convention: random_text_XXXX.txt (where XXXX = 0001-1000)\n")
    f.write(f"\nContent Statistics:\n")
    f.write(f"  - Minimum Length: {MIN_LENGTH} characters\n")
    f.write(f"  - Maximum Length: {MAX_ENCODING} characters\n")
    f.write(f"  - Average Length: ~{(MIN_LENGTH + MAX_LENGTH) / 2:.0f} characters\n")
    f.write("\n" + "=" * 60 + "\n")

print(f"\n📄 Summary report saved to: {summary_path}")