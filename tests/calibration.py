import os
import sys
import torch
import numpy as np
from pathlib import Path

# Ensure the agent root is in the path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from agent.vision.biomed_classifier import BioCLIPClassifier

# ----------------- CONFIGURATION -----------------
GROUND_TRUTH_DIR = r"F:\Users\myfri\Downloads\LabeledCrops(Test)"
REFERENCE_DIR = r"F:\Users\myfri\Downloads\EmptyLabels(Test)"
INPUT_CROPS_DIR = r"F:\Users\myfri\Downloads\Crops (Test)"
# -------------------------------------------------

def run_calibration():
    print(f"\n[{'='*50}]")
    print("🚀 BIOCLIP SIMILARITY CALIBRATOR")
    print(f"[{'='*50}]\n")
    
    print("🗺️ Mapping ground truth from LabeledCrops(Test)...")
    ground_truth = {}
    for root, dirs, files in os.walk(GROUND_TRUTH_DIR):
        for f in files:
            cat = os.path.basename(root)
            ground_truth[f] = cat
            
    reference_images_dict = {}
    categories = []
    print("📸 Fetching reference images...")
    for d in os.listdir(REFERENCE_DIR):
        folder_path = os.path.join(REFERENCE_DIR, d)
        if os.path.isdir(folder_path) and d != "Background":
            categories.append(d)
            reference_images_dict[d] = []
            for f in os.listdir(folder_path):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff')):
                    reference_images_dict[d].append(os.path.join(folder_path, f))
                    
    print("⚙️ Initializing BioCLIP...")
    classifier = BioCLIPClassifier()
    device = classifier.device
    model = classifier.model
    preprocess = classifier.preprocess
    
    # Encode all references
    print("🧠 Encoding reference images...")
    all_ref_feats = []
    all_ref_labels = []
    for cat in categories:
        for p in reference_images_dict[cat]:
            try:
                from PIL import Image
                ref_img = Image.open(p).convert("RGB")
                ref_input = preprocess(ref_img).unsqueeze(0).to(device)
                with torch.no_grad():
                    f = model.encode_image(ref_input)
                    f /= f.norm(dim=-1, keepdim=True)
                all_ref_feats.append(f)
                all_ref_labels.append(cat)
            except Exception as e:
                print(f"Failed to load reference {p}: {e}")
                
    if not all_ref_feats:
        print("❌ No reference images found!")
        return
        
    ref_features_tensor = torch.cat(all_ref_feats, dim=0).to(device)
    
    print("🔬 Scanning input crops...")
    bg_similarities = []
    fg_similarities = []
    
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
            
        try:
            from PIL import Image
            image = Image.open(filepath).convert("RGB")
            image_input = preprocess(image).unsqueeze(0).to(device)
            with torch.no_grad():
                target_features = model.encode_image(image_input)
                target_features /= target_features.norm(dim=-1, keepdim=True)
                
                # Raw cosine similarities against all references (-1.0 to 1.0)
                raw_similarities = (target_features @ ref_features_tensor.T)[0]
                max_sim = raw_similarities.max().item()
                
                if true_cat == "Background":
                    bg_similarities.append(max_sim)
                else:
                    fg_similarities.append(max_sim)
                    
        except Exception:
            pass
            
        if (i+1) % 50 == 0:
            print(f"Processed {i+1}/{len(files_to_process)}...")
            
    print("\n📊 CALIBRATION RESULTS:")
    
    bg_sims = np.array(bg_similarities)
    fg_sims = np.array(fg_similarities)
    
    if len(bg_sims) > 0:
        print(f"\nBackground Noise Images (n={len(bg_sims)}):")
        print(f"  Min Sim: {bg_sims.min():.4f}")
        print(f"  Mean Sim: {bg_sims.mean():.4f}")
        print(f"  75th Percentile: {np.percentile(bg_sims, 75):.4f}")
        print(f"  95th Percentile: {np.percentile(bg_sims, 95):.4f}")
        print(f"  Max Sim: {bg_sims.max():.4f}")
        
    if len(fg_sims) > 0:
        print(f"\nForeground/Structure Images (n={len(fg_sims)}):")
        print(f"  Min Sim: {fg_sims.min():.4f}")
        print(f"  5th Percentile: {np.percentile(fg_sims, 5):.4f}")
        print(f"  25th Percentile: {np.percentile(fg_sims, 25):.4f}")
        print(f"  Mean Sim: {fg_sims.mean():.4f}")
        print(f"  Max Sim: {fg_sims.max():.4f}")
        
    if len(bg_sims) > 0 and len(fg_sims) > 0:
        p95_bg = np.percentile(bg_sims, 95)
        p05_fg = np.percentile(fg_sims, 5)
        
        print("\n💡 RECOMMENDATION:")
        print(f"To filter out 95% of background noise, set BIOCLIP_SIMILARITY_THRESHOLD > {p95_bg:.4f}")
        print(f"To capture 95% of real structures, set BIOCLIP_SIMILARITY_THRESHOLD < {p05_fg:.4f}")
        
        optimal = (p95_bg + p05_fg) / 2
        print(f"Suggested Optimal Threshold: {optimal:.4f}")

if __name__ == "__main__":
    run_calibration()
