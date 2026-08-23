import os
import shutil
import random
import argparse

def main():
    parser = argparse.ArgumentParser(description="Randomly sample N images from a large folder")
    parser.add_argument("--src", required=True, help="Source folder with massive amounts of crops")
    parser.add_argument("--dest", required=True, help="Destination folder for the subset")
    parser.add_argument("--count", type=int, default=1000, help="Number of images to copy")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.src):
        print(f"Error: Source {args.src} does not exist.")
        return
        
    os.makedirs(args.dest, exist_ok=True)
    
    print(f"Scanning {args.src} for images...")
    all_files = []
    for root, _, files in os.walk(args.src):
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')):
                all_files.append(os.path.join(root, f))
                
    if len(all_files) == 0:
        print("No images found in source directory.")
        return
        
    print(f"Found {len(all_files)} images.")
    sample_size = min(args.count, len(all_files))
    sampled_files = random.sample(all_files, sample_size)
    
    print(f"Copying {sample_size} random images to {args.dest}...")
    for i, file_path in enumerate(sampled_files):
        filename = os.path.basename(file_path)
        dest_path = os.path.join(args.dest, f"{i:06d}_{filename}") # prepend index to avoid name collisions
        shutil.copy2(file_path, dest_path)
        
    print(f"\nDone! Sampled {sample_size} images into: {args.dest}")

if __name__ == "__main__":
    main()
