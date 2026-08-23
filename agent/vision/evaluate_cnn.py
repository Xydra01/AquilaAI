import os
import torch
from torchvision import transforms, models
from PIL import Image

from dotenv import load_dotenv

def evaluate_gold_standard():
    load_dotenv()
    test_dir = os.getenv("CNN_EVAL_DIR", r"F:\Users\myfri\Downloads\NewGoldStandard")
    model_path = r"F:\Users\myfri\agent-projects\models\custom_diatom_resnet.pth"
    
    if not os.path.exists(model_path):
        print("Error: Model not found at", model_path)
        return
        
    # We must match the classes used during training!
    # Hardcoding them since they were saved in the model state or known:
    classes = sorted([d for d in os.listdir(test_dir) if os.path.isdir(os.path.join(test_dir, d))])
    class_to_idx = {cls_name: i for i, cls_name in enumerate(classes)}
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    # Initialize Model
    model = models.resnet18(weights=None)
    num_ftrs = model.fc.in_features
    model.fc = torch.nn.Linear(num_ftrs, len(classes))
    model.load_state_dict(torch.load(model_path, map_location=device))
    model = model.to(device)
    model.eval()
    
    # Validation transforms must match train_cnn.py
    val_transforms = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    total = 0
    correct = 0
    class_correct = {c: 0 for c in classes}
    class_total = {c: 0 for c in classes}
    
    print("Evaluating CNN on Gold Standard Dataset...")
    
    with torch.no_grad():
        for class_name in classes:
            class_dir = os.path.join(test_dir, class_name)
            for f in os.listdir(class_dir):
                if not f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')):
                    continue
                    
                img_path = os.path.join(class_dir, f)
                try:
                    image = Image.open(img_path).convert("RGB")
                    tensor = val_transforms(image).unsqueeze(0).to(device)
                    
                    outputs = model(tensor)
                    probabilities = torch.nn.functional.softmax(outputs, dim=1)
                    max_prob, preds = torch.max(probabilities, 1)
                    
                    pred_idx = preds.item()
                    pred_class = classes[pred_idx]
                    
                    confidence_threshold = float(os.getenv("CNN_AMORPHOUS_THRESHOLD", "0.60"))
                    if max_prob.item() < confidence_threshold and "Amorphous" in classes:
                        pred_class = "Amorphous"
                    
                    total += 1
                    class_total[class_name] += 1
                    
                    if pred_class == class_name:
                        correct += 1
                        class_correct[class_name] += 1
                except Exception as e:
                    print(f"Error processing {img_path}: {e}")
                    
    print("\n--- RESULTS ---")
    print(f"Overall Accuracy: {correct}/{total} ({(correct/total)*100:.2f}%)")
    print("\nPer-Class Accuracy:")
    for c in classes:
        if class_total[c] > 0:
            acc = (class_correct[c] / class_total[c]) * 100
            print(f"  - {c}: {acc:.2f}% ({class_correct[c]}/{class_total[c]})")
        else:
            print(f"  - {c}: N/A (0 images)")

if __name__ == "__main__":
    evaluate_gold_standard()
