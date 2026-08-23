import os
import json
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image

class CNNClassifier:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CNNClassifier, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model_path = os.getenv("CNN_MODEL_PATH", "models/custom_diatom_resnet.pth")
        self.classes_path = os.getenv("CNN_CLASSES_PATH", "models/cnn_classes.json")
        
        if not os.path.exists(self.model_path) or not os.path.exists(self.classes_path):
            print(f"⚠️ Model or classes file missing. Please run train_cnn.py first.")
            self.model = None
            self.classes = []
            return
            
        with open(self.classes_path, "r") as f:
            self.classes = json.load(f)
            
        self.model = models.resnet18(weights=None)
        num_ftrs = self.model.fc.in_features
        self.model.fc = nn.Linear(num_ftrs, len(self.classes))
        self.model.load_state_dict(torch.load(self.model_path, map_location=self.device, weights_only=True))
        self.model = self.model.to(self.device)
        self.model.eval()
        
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])
        
        self._initialized = True

    def classify(self, image_path: str, categories: list[str] = None, reference_images_dict: dict = None) -> str:
        """
        Takes an image path and returns the predicted category using the trained CNN.
        The categories list and reference dict are kept in the signature to match the interface, 
        but they are ignored because the CNN has its own trained classes.
        """
        if self.model is None:
            return "Background" # Fail-safe fallback
            
        try:
            image = Image.open(image_path).convert("RGB")
            input_tensor = self.transform(image).unsqueeze(0).to(self.device)
            
            with torch.no_grad():
                outputs = self.model(input_tensor)
                probabilities = torch.nn.functional.softmax(outputs, dim=1)
                max_prob, preds = torch.max(probabilities, 1)
                
            predicted_class = self.classes[preds.item()]
            
            # AMORPHOUS CATCH-ALL THRESHOLD
            # If the network is confused (low confidence), assume it's Amorphous
            confidence_threshold = float(os.getenv("CNN_AMORPHOUS_THRESHOLD", "0.60"))
            if max_prob.item() < confidence_threshold and "Amorphous" in self.classes:
                predicted_class = "Amorphous"
                
            return predicted_class
            # but the model only knows what it was trained on!
            return predicted_class
            
        except Exception as e:
            print(f"CNN error classifying {image_path}: {e}")
            return "ignore"
