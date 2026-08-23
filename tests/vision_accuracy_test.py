import os
import shutil
import sys
from pathlib import Path
from collections import defaultdict

# Ensure the agent root is in the path
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from agent.tasks.data_processor import run_data_processing

# ----------------- CONFIGURATION -----------------
GROUND_TRUTH_DIR = r"F:\Users\myfri\Downloads\LabeledCrops(Test)"
REFERENCE_DIR = r"F:\Users\myfri\Downloads\EmptyLabels(Test)"
INPUT_CROPS_DIR = r"F:\Users\myfri\Downloads\Crops (Test)"
SANDBOX_DIR = r"F:\Users\myfri\Downloads\Sandbox_EmptyLabels_Test"
# -------------------------------------------------

def mock_ui(msg):
    # Print the progress from the data processor
    print(msg, end="")

def run_test():
    print(f"\n[{'='*50}]")
    print("VISION ACCURACY TEST SUITE (Custom CNN)")
    print(f"[{'='*50}]\n")

    # 1. Prepare Sandbox Directory
    print("Preparing sandbox directory...")
    if os.path.exists(SANDBOX_DIR):
        shutil.rmtree(SANDBOX_DIR)
    shutil.copytree(REFERENCE_DIR, SANDBOX_DIR)
    
    # 2. Map Ground Truth
    print("Mapping ground truth from LabeledCrops(Test)...")
    ground_truth = {}
    if not os.path.exists(GROUND_TRUTH_DIR):
        print(f"Ground truth directory not found: {GROUND_TRUTH_DIR}")
        return
        
    for root, dirs, files in os.walk(GROUND_TRUTH_DIR):
        for f in files:
            cat = os.path.basename(root)
            ground_truth[f] = cat
            
    # 3. Run Data Processing
    print("\nRunning Custom CNN Classifier...")
    user_input = f"[Data Mode Input: {INPUT_CROPS_DIR}]\n[Data Mode Output: {SANDBOX_DIR}]\n\nTest Run"
    try:
        run_data_processing(user_input, "test_vision_suite", mock_ui, lambda: False)
    except Exception as e:
        print(f"\nPipeline crashed: {e}")
        import traceback
        traceback.print_exc()
        return

    # 4. Evaluate Accuracy
    print("\nEvaluating Accuracy...")
    
    # Map predictions from sandbox
    predictions = {}
    for root, dirs, files in os.walk(SANDBOX_DIR):
        cat = os.path.basename(root)
        for f in files:
            predictions[f] = cat
            
    # Scorecard Data Structures
    categories = sorted(list(set(ground_truth.values())))
    correct_by_cat = defaultdict(int)
    total_by_cat = defaultdict(int)
    misclassified = []

    total_correct = 0
    total_scored = 0

    # Score only the files from the input crops (ignore pre-existing reference images)
    for root, dirs, files in os.walk(INPUT_CROPS_DIR):
        for f in files:
            if not f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff')):
                continue
                
            true_cat = ground_truth.get(f)
            if not true_cat:
                continue # Skip files we don't have a ground truth for
                
            pred_cat = predictions.get(f)
            if not pred_cat:
                # If it wasn't sorted, count it as a miss or ignore?
                # The pipeline puts it in 'ignore' or skips it.
                pred_cat = "Unclassified"
                
            total_by_cat[true_cat] += 1
            total_scored += 1
            
            if true_cat == pred_cat:
                correct_by_cat[true_cat] += 1
                total_correct += 1
            else:
                misclassified.append((f, true_cat, pred_cat))

    # 5. Print Scorecard
    print(f"\n[{'='*50}]")
    print("📈 FINAL SCORECARD")
    print(f"[{'='*50}]\n")
    
    if total_scored == 0:
        print("❌ No input crops matched the ground truth mapping!")
        return
        
    overall_acc = (total_correct / total_scored) * 100
    print(f"🌟 Overall Accuracy: {overall_acc:.2f}% ({total_correct}/{total_scored})\n")
    
    print(f"{'Category':<25} | {'Accuracy':<10} | {'Correct / Total'}")
    print("-" * 60)
    for cat in categories:
        tot = total_by_cat[cat]
        if tot == 0:
            continue
        corr = correct_by_cat[cat]
        acc = (corr / tot) * 100
        print(f"{cat:<25} | {acc:>6.2f}%    | {corr} / {tot}")

    if misclassified:
        print("\n\n📉 Misclassified Files Log:")
        print(f"{'Filename':<25} | {'True Category':<25} | {'Predicted Category'}")
        print("-" * 80)
        # Show top 20 misclassifications
        for f, t, p in misclassified[:20]:
            print(f"{f:<25} | {t:<25} | {p}")
        if len(misclassified) > 20:
            print(f"... and {len(misclassified) - 20} more.")

if __name__ == "__main__":
    run_test()
