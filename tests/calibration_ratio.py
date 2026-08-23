import os
import sys
import numpy as np
import cv2
from PIL import Image

GROUND_TRUTH_DIR = r"F:\Users\myfri\Downloads\LabeledCrops(Test)"
INPUT_CROPS_DIR = r"F:\Users\myfri\Downloads\Crops (Test)"

def get_foreground_ratio(image_path):
    pil_image = Image.open(image_path).convert("RGB")
    img = np.array(pil_image)
    if len(img.shape) == 3 and img.shape[2] == 3:
        img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    else:
        gray = img
        
    edges = cv2.Canny(gray, 50, 150)
    return np.count_nonzero(edges) / edges.size

def run_calibration():
    print("FOREGROUND RATIO CALIBRATOR")
    
    ground_truth = {}
    for root, dirs, files in os.walk(GROUND_TRUTH_DIR):
        for f in files:
            cat = os.path.basename(root)
            ground_truth[f] = cat
            
    bg_ratios = []
    fg_ratios = []
    
    files_to_process = []
    for root, dirs, files in os.walk(INPUT_CROPS_DIR):
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff')):
                files_to_process.append(os.path.join(root, f))
                
    for i, filepath in enumerate(files_to_process):
        filename = os.path.basename(filepath)
        true_cat = ground_truth.get(filename)
        if not true_cat:
            continue
            
        ratio = get_foreground_ratio(filepath)
        if true_cat == "Background":
            bg_ratios.append(ratio)
        else:
            fg_ratios.append(ratio)
            
    bg_arr = np.array(bg_ratios)
    fg_arr = np.array(fg_ratios)
    
    print(f"\nBackground Noise Images (n={len(bg_arr)}):")
    print(f"  Mean Ratio: {bg_arr.mean():.4f}")
    print(f"  50th Percentile: {np.percentile(bg_arr, 50):.4f}")
    print(f"  90th Percentile: {np.percentile(bg_arr, 90):.4f}")
    print(f"  Max Ratio: {bg_arr.max():.4f}")
    
    print(f"\nForeground/Structure Images (n={len(fg_arr)}):")
    print(f"  Min Ratio: {fg_arr.min():.4f}")
    print(f"  10th Percentile: {np.percentile(fg_arr, 10):.4f}")
    print(f"  Mean Ratio: {fg_arr.mean():.4f}")
    print(f"  Max Ratio: {fg_arr.max():.4f}")

if __name__ == "__main__":
    run_calibration()
