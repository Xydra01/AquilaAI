import os
import torch
from PIL import Image
from transformers import pipeline

def test_detector():
    print("Loading Owl-ViT Zero-Shot Detector...")
    device = 0 if torch.cuda.is_available() else -1
    detector = pipeline(task="zero-shot-object-detection", model="google/owlvit-base-patch32", device=device)
    
    bg_dir = r"F:\Users\myfri\Downloads\LabeledCrops(Test)\Background"
    fg_dir = r"F:\Users\myfri\Downloads\LabeledCrops(Test)\Round Particles"
    
    print("\nTesting Background Images:")
    bg_files = [f for f in os.listdir(bg_dir) if f.endswith('.tif')][:5]
    for f in bg_files:
        img_path = os.path.join(bg_dir, f)
        img = Image.open(img_path).convert("RGB")
        preds = detector(
            img,
            candidate_labels=["particle", "microbe", "structure", "cell"]
        )
        print(f"{f}: {len(preds)} objects found. Best score: {preds[0]['score'] if preds else 0}")
        
    print("\nTesting Structure Images:")
    fg_files = [f for f in os.listdir(fg_dir) if f.endswith('.tif')][:5]
    for f in fg_files:
        img_path = os.path.join(fg_dir, f)
        img = Image.open(img_path).convert("RGB")
        preds = detector(
            img,
            candidate_labels=["particle", "microbe", "structure", "cell"]
        )
        print(f"{f}: {len(preds)} objects found. Best score: {preds[0]['score'] if preds else 0}")

if __name__ == "__main__":
    test_detector()
