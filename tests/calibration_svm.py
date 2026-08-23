import os
import torch
from PIL import Image
import open_clip
import numpy as np
from sklearn.svm import SVC
from sklearn.metrics import accuracy_score

REFERENCE_DIR = r"F:\Users\myfri\Downloads\EmptyLabels(Test)"
TARGET_DIR = r"F:\Users\myfri\Downloads\Crops (Test)"
GROUND_TRUTH_DIR = r"F:\Users\myfri\Downloads\LabeledCrops(Test)"

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model, _, preprocess = open_clip.create_model_and_transforms('hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224')
model = model.to(device)
model.eval()

def encode_image(img_path):
    try:
        img = Image.open(img_path).convert("RGB")
        img_input = preprocess(img).unsqueeze(0).to(device)
        with torch.no_grad():
            f = model.encode_image(img_input)
            f /= f.norm(dim=-1, keepdim=True)
            return f.cpu().numpy()[0]
    except Exception:
        return None

def run():
    print("Training SVM on Reference Images...")
    X_train = []
    y_train = []
    
    categories = []
    for d in os.listdir(REFERENCE_DIR):
        folder_path = os.path.join(REFERENCE_DIR, d)
        if os.path.isdir(folder_path):
            categories.append(d)
            for f in os.listdir(folder_path):
                img_path = os.path.join(folder_path, f)
                feat = encode_image(img_path)
                if feat is not None:
                    X_train.append(feat)
                    y_train.append(d)
                    
    clf = SVC(kernel='linear', C=1.0, class_weight='balanced')
    clf.fit(X_train, y_train)
    
    print("Mapping Ground Truth...")
    ground_truth = {}
    for root, dirs, files in os.walk(GROUND_TRUTH_DIR):
        for f in files:
            cat = os.path.basename(root)
            ground_truth[f] = cat
            
    print("Evaluating Test Images...")
    y_true = []
    y_pred = []
    
    for root, dirs, files in os.walk(TARGET_DIR):
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff')):
                img_path = os.path.join(root, f)
                true_cat = ground_truth.get(f)
                if not true_cat: continue
                
                feat = encode_image(img_path)
                if feat is not None:
                    pred = clf.predict([feat])[0]
                    y_true.append(true_cat)
                    y_pred.append(pred)
                    
    acc = accuracy_score(y_true, y_pred)
    print(f"\nSVM Overall Accuracy: {acc * 100:.2f}%")
    
    # Calculate per category
    for cat in categories:
        true_for_cat = [1 for t in y_true if t == cat]
        if len(true_for_cat) == 0: continue
        correct = sum(1 for t, p in zip(y_true, y_pred) if t == cat and p == cat)
        print(f"{cat}: {correct/len(true_for_cat)*100:.2f}% ({correct}/{len(true_for_cat)})")

if __name__ == "__main__":
    run()
