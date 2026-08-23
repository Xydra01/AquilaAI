import torch
from PIL import Image
import open_clip
import os

class BioCLIPClassifier:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BioCLIPClassifier, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # Load the BioCLIP model
        self.model, _, self.preprocess = open_clip.create_model_and_transforms(
            'hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224'
        )
        self.model = self.model.to(self.device)
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer('hf-hub:microsoft/BiomedCLIP-PubMedBERT_256-vit_base_patch16_224')
        self._initialized = True


    def classify(self, image_path: str, categories: list[str], reference_images_dict: dict = None) -> str:
        """
        Takes an image path, a list of category names, and optionally a dictionary mapping categories to lists of reference image paths.
        Returns the category name that best matches the image.
        """
        text_weight = float(os.getenv("BIOCLIP_TEXT_WEIGHT", "0.2"))
        sim_threshold = float(os.getenv("BIOCLIP_SIMILARITY_THRESHOLD", "0.24"))
        
        try:
            image = Image.open(image_path).convert("RGB")
            image_input = self.preprocess(image).unsqueeze(0).to(self.device)
            
            with torch.no_grad():
                target_features = self.model.encode_image(image_input)
                target_features /= target_features.norm(dim=-1, keepdim=True)
                
                # 1. Zero-shot text embeddings
                prompts = [f"microscopy image of {cat.lower()}" for cat in categories]
                text_input = self.tokenizer(prompts).to(self.device)
                text_features = self.model.encode_text(text_input)
                text_features /= text_features.norm(dim=-1, keepdim=True)
                
                similarity_text = (100.0 * target_features @ text_features.T).softmax(dim=-1)[0]
                
                # 2. Few-shot image embeddings (if references are provided)
                if reference_images_dict:
                    all_ref_feats = []
                    all_ref_labels = []
                    
                    for cat in categories:
                        paths = reference_images_dict.get(cat, [])
                        for p in paths:
                            try:
                                ref_img = Image.open(p).convert("RGB")
                                ref_input = self.preprocess(ref_img).unsqueeze(0).to(self.device)
                                f = self.model.encode_image(ref_input)
                                f /= f.norm(dim=-1, keepdim=True)
                                all_ref_feats.append(f)
                                all_ref_labels.append(cat)
                            except Exception:
                                pass
                                
                    if all_ref_feats:
                        ref_features_tensor = torch.cat(all_ref_feats, dim=0).to(self.device)
                        
                        # Compute similarity between target and ALL individual reference images
                        similarity_matrix = (100.0 * target_features @ ref_features_tensor.T).softmax(dim=-1)[0]
                        
                        # 1-Nearest Neighbor mapping: Map the highest individual image score to its category
                        category_scores = torch.zeros(len(categories)).to(self.device)
                        for i, label in enumerate(all_ref_labels):
                            cat_idx = categories.index(label)
                            if similarity_matrix[i] > category_scores[cat_idx]:
                                category_scores[cat_idx] = similarity_matrix[i]
                                
                        # Normalize the image scores
                        if category_scores.sum() > 0:
                            category_scores /= category_scores.sum()
                            
                        # Combine similarities using configurable weight
                        combined_similarity = text_weight * similarity_text + (1.0 - text_weight) * category_scores
                        top_idx = combined_similarity.argmax()
                        
                        raw_similarities = (target_features @ ref_features_tensor.T)[0]
                        max_raw_sim = raw_similarities.max().item()
                    else:
                        top_idx = similarity_text.argmax()
                        max_raw_sim = (target_features @ text_features.T)[0].max().item()
                else:
                    top_idx = similarity_text.argmax()
                    max_raw_sim = (target_features @ text_features.T)[0].max().item()
                    
                if max_raw_sim < sim_threshold and "Background" in categories:
                    return "Background"
                    
                return categories[top_idx.item()]
        except Exception as e:
            # Fallback in case of corruption or unreadable file
            print(f"BioCLIP error classifying {image_path}: {e}")
            return "ignore"
