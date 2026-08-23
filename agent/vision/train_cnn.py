import os
import json
import torch
import torch.nn as nn
import torch.optim as optim
from torchvision import models, transforms
from torch.utils.data import Dataset, DataLoader, random_split
from PIL import Image

class MultiDirDataset(Dataset):
    def __init__(self, directories, transform=None):
        self.transform = transform
        self.image_paths = []
        self.labels = []
        self.classes = set()
        
        # First pass: find all unique classes
        for d in directories:
            if not os.path.isdir(d):
                continue
            for class_name in os.listdir(d):
                class_dir = os.path.join(d, class_name)
                if os.path.isdir(class_dir):
                    self.classes.add(class_name)
                    
        self.classes = sorted(list(self.classes))
        self.class_to_idx = {cls_name: i for i, cls_name in enumerate(self.classes)}
        
        # Second pass: collect all images
        for d in directories:
            if not os.path.isdir(d):
                continue
            for class_name in os.listdir(d):
                class_dir = os.path.join(d, class_name)
                if os.path.isdir(class_dir):
                    for img_name in os.listdir(class_dir):
                        if img_name.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')):
                            self.image_paths.append(os.path.join(class_dir, img_name))
                            self.labels.append(self.class_to_idx[class_name])
                            
    def __len__(self):
        return len(self.image_paths)
        
    def __getitem__(self, idx):
        img_path = self.image_paths[idx]
        image = Image.open(img_path).convert("RGB")
        label = self.labels[idx]
        
        if self.transform:
            image = self.transform(image)
            
        return image, label

def train_active_learning_cnn(directories, epochs=20, batch_size=32, save_dir="models"):
    print("INITIALIZING ACTIVE LEARNING RESNET-18...")
    
    os.makedirs(save_dir, exist_ok=True)
    
    # Advanced Data Augmentation to simulate variations of rare particles
    train_transforms = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomVerticalFlip(),
        transforms.RandomRotation(45),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2), # Simulates lighting changes
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    val_transforms = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    full_dataset = MultiDirDataset(directories, transform=None)
    
    if len(full_dataset) == 0:
        print("No images found in the specified directories!")
        return
        
    # Split dataset 80/20
    train_size = int(0.8 * len(full_dataset))
    val_size = len(full_dataset) - train_size
    
    train_dataset, val_dataset = random_split(full_dataset, [train_size, val_size])
    
    # Assign specific transforms
    train_dataset.dataset.transform = train_transforms
    
    # We must apply val_transforms to val_dataset. 
    # Since random_split creates Subset objects, we wrap it in a custom class to override transforms.
    class WrappedSubset(Dataset):
        def __init__(self, subset, transform):
            self.subset = subset
            self.transform = transform
        def __len__(self): return len(self.subset)
        def __getitem__(self, idx):
            img_path = self.subset.dataset.image_paths[self.subset.indices[idx]]
            label = self.subset.dataset.labels[self.subset.indices[idx]]
            image = Image.open(img_path).convert("RGB")
            if self.transform: image = self.transform(image)
            return image, label
            
    val_dataset = WrappedSubset(val_dataset, val_transforms)
    
    # Extract labels from the train subset to build the WeightedRandomSampler
    train_labels = [train_dataset.dataset.labels[i] for i in train_dataset.indices]
    from collections import Counter
    train_class_counts = Counter(train_labels)
    
    # Weight per sample = 1.0 / frequency of its class
    sample_weights = [1.0 / train_class_counts[label] for label in train_labels]
    
    from torch.utils.data import WeightedRandomSampler
    # This automatically undersamples Background and oversamples Square Particles!
    sampler = WeightedRandomSampler(weights=sample_weights, num_samples=len(sample_weights), replacement=True)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, sampler=sampler)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    
    num_classes = len(full_dataset.classes)
    print(f"Classes Map: {full_dataset.class_to_idx}")
    print(f"Training on {train_size} images, Validating on {val_size} images.")
    
    # Save the class mapping so the classifier knows what indices mean!
    mapping_path = os.path.join(save_dir, "cnn_classes.json")
    with open(mapping_path, "w") as f:
        json.dump(full_dataset.classes, f)
        
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    model = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    num_ftrs = model.fc.in_features
    model.fc = nn.Linear(num_ftrs, num_classes)
    model = model.to(device)
    
    # Since we are using a WeightedRandomSampler to literally physically balance the mini-batches,
    # we DO NOT need mathematical class_weights in the CrossEntropyLoss anymore!
    # Double dipping (oversampling + weighting) would explode the gradients.
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode='max', factor=0.5, patience=3, verbose=True)
    
    best_acc = 0.0
    model_save_path = os.path.join(save_dir, "custom_diatom_resnet.pth")
    
    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        running_corrects = 0
        
        for inputs, labels in train_loader:
            inputs = inputs.to(device)
            labels = labels.to(device)
            
            optimizer.zero_grad()
            outputs = model(inputs)
            _, preds = torch.max(outputs, 1)
            loss = criterion(outputs, labels)
            
            loss.backward()
            optimizer.step()
            
            running_loss += loss.item() * inputs.size(0)
            running_corrects += torch.sum(preds == labels.data)
            
        epoch_acc = running_corrects.double() / train_size
        
        # Validation
        model.eval()
        val_corrects = 0
        
        with torch.no_grad():
            for inputs, labels in val_loader:
                inputs = inputs.to(device)
                labels = labels.to(device)
                outputs = model(inputs)
                _, preds = torch.max(outputs, 1)
                val_corrects += torch.sum(preds == labels.data)
                
        val_acc = val_corrects.double() / val_size
        scheduler.step(val_acc)
        
        print(f"Epoch {epoch+1}/{epochs} - Train Acc: {epoch_acc:.4f} | Val Acc: {val_acc:.4f}")
        
        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(model.state_dict(), model_save_path)
            
    print(f"\nTraining Complete! Best Val Acc: {best_acc:.4f}")
    print(f"Model saved to: {model_save_path}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    # Read training directories from .env, fallback to test directories
    dirs_env = os.getenv("CNN_TRAINING_DIRECTORIES", "")
    if dirs_env:
        directories = [d.strip() for d in dirs_env.split(',')]
    else:
        directories = [
            r"F:\Users\myfri\Downloads\LabeledCrops(Test)",
            r"F:\Users\myfri\Downloads\EmptyLabels(Test)"
        ]
        
    print(f"Loading training data from: {directories}")
        
    epochs = int(os.getenv("CNN_TRAINING_EPOCHS", "20"))
    train_active_learning_cnn(directories, epochs=epochs)
