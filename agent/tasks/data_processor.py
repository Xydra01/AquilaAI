import os
import shutil
import json
import traceback
from pathlib import Path

from agent.core import get_agent
from agent.coding.file_parser import _dispatch_parse, MAX_FILE_BYTES

def run_data_processing(user_input: str, instance_id: str, ui_callback, cancel_check):
    """
    Piecemeal data processing: reads input folder, processes files one-by-one,
    wipes context between files, and passes a running summary.
    """
    ui_callback("🚀 Starting Data Processing...\n")
    
    # Parse input and output directories from the user_input
    # Format from GUI: [Data Mode Input: /path]\n[Data Mode Output: /path]\n\nPrompt
    lines = user_input.split("\n")
    input_dir = ""
    output_dir = ""
    prompt_lines = []
    
    for line in lines:
        if line.startswith("[Data Mode Input:"):
            input_dir = line.split("Input:")[1].strip(" ]")
        elif line.startswith("[Data Mode Output:"):
            output_dir = line.split("Output:")[1].strip(" ]")
        else:
            prompt_lines.append(line)
            
    rules_prompt = "\n".join(prompt_lines).strip()
    
    if not input_dir or not os.path.isdir(input_dir):
        ui_callback(f"❌ Error: Invalid input directory: {input_dir}\n")
        return
        
    if not output_dir:
        ui_callback("❌ Error: No output directory specified.\n")
        return
        
    os.makedirs(output_dir, exist_ok=True)
    ui_callback(f"📂 Input: {input_dir}\n📂 Output: {output_dir}\n📋 Rules: {rules_prompt}\n\n")

    agent = get_agent(instance_id)
    running_summary = "No files processed yet."
    processed_count = 0
    error_count = 0

    existing_folders = [d for d in os.listdir(output_dir) if os.path.isdir(os.path.join(output_dir, d))]
    folder_list_str = ", ".join(f'"{d}"' for d in existing_folders) if existing_folders else "None"

    reference_images = []
    reference_descriptions = []
    reference_images_dict = {}
    
    ui_callback("📸 Fetching category reference examples (up to 3 per category)...\n")
    for d in existing_folders:
        folder_path = os.path.join(output_dir, d)
        reference_images_dict[d] = []
        count = 0
        for f in os.listdir(folder_path):
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff')):
                ref_path = os.path.join(folder_path, f)
                try:
                    # Keep path for BioCLIP few-shot
                    reference_images_dict[d].append(ref_path)
                    
                    # Also parse the first one for the LLM fallback just in case
                    if count == 0:
                        import mimetypes
                        ref_mime, _ = mimetypes.guess_type(ref_path)
                        with open(ref_path, "rb") as rf:
                            ref_bytes = rf.read()
                        ref_parsed = _dispatch_parse(ref_path, ref_bytes, os.path.basename(ref_path), ref_mime)
                        if ref_parsed["type"] == "image":
                            reference_images.append(ref_parsed["payload"])
                            reference_descriptions.append(d)
                            
                    count += 1
                    # We load all reference images for BioCLIP KNN
                    # Only the first one is loaded into RAM for the LLM fallback
                except Exception as e:
                    pass
    
    if reference_descriptions:
        ui_callback(f"🖼️ Attached visual references for: {', '.join(reference_descriptions)}\n\n")

    # Scan files
    files_to_process = []
    for root, _, files in os.walk(input_dir):
        for f in files:
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp')):
                files_to_process.append(os.path.join(root, f))
            
    total_files = len(files_to_process)
    ui_callback(f"🔍 Found {total_files} files to process.\n\n")

    for idx, filepath in enumerate(files_to_process):
        if cancel_check and cancel_check():
            ui_callback("🛑 Data processing cancelled by user.\n")
            break
            
        ui_callback(f"⏳ Processing [{idx+1}/{total_files}]: {os.path.basename(filepath)}... ")
        
        try:
            size = os.path.getsize(filepath)
            if size > MAX_FILE_BYTES:
                ui_callback(f"Skipped (Exceeds {MAX_FILE_BYTES/1024/1024:.1f}MB)\n")
                continue
            if filepath.lower().endswith('.txt'):
                ui_callback(f"⏭️ Ignored (Text file): {os.path.basename(filepath)}\n")
                processed_count += 1
                continue
                
            with open(filepath, "rb") as f:
                file_bytes = f.read()
            import mimetypes
            mime_type, _ = mimetypes.guess_type(filepath)
            
            # _dispatch_parse expects: path, file_bytes, file_name, mime_type
            parsed = _dispatch_parse(filepath, file_bytes, os.path.basename(filepath), mime_type)
            
            # Prepare file context
            if parsed["type"] == "text":
                content_preview = parsed["payload"][:15000] # Cap size 
                image_payloads = reference_images.copy()
            elif parsed["type"] == "image":
                ui_callback(f"🧠 Analyzing with CNN...\n")
                from agent.vision.cnn_classifier import CNNClassifier
                classifier = CNNClassifier()
                
                dest_folder = classifier.classify(filepath, existing_folders, reference_images_dict)
                
                if dest_folder != "ignore" and dest_folder in existing_folders:
                    target_dir = os.path.join(output_dir, dest_folder)
                    os.makedirs(target_dir, exist_ok=True)
                    target_path = os.path.join(target_dir, os.path.basename(filepath))
                    shutil.copy2(filepath, target_path)
                    ui_callback(f"✅ Copied to {dest_folder}/\n")
                else:
                    ui_callback("⏭️ Ignored\n")
                    
                processed_count += 1
                continue # Skip the Ollama logic for images
            else:
                content_preview = "[Unsupported or binary file]"
                image_payloads = reference_images.copy()
                
            ref_mapping_text = ""
            if reference_descriptions:
                ref_mapping_text = "VISUAL REFERENCES PROVIDED:\n"
                for i, ref_cat in enumerate(reference_descriptions):
                    ref_mapping_text += f"- Image {i+1} is a confirmed example of category '{ref_cat}'.\n"
                ref_mapping_text += f"- The FINAL image (Image {len(reference_descriptions)+1}) is the target file you must classify.\n\n"
                
            sys_prompt = (
                "You are an autonomous data processing agent.\n"
                "Your objective is to review the current file and decide if it needs to be sorted (moved) to a subfolder in the output directory.\n\n"
                f"AVAILABLE CATEGORIES (Existing Folders): {folder_list_str}\n"
                "Unless the user explicitly instructs you to create new folders, you MUST sort files ONLY into one of the AVAILABLE CATEGORIES listed above.\n\n"
                f"{ref_mapping_text}"
                "You MUST place your step-by-step visual analysis of the target image inside <think>...</think> tags BEFORE outputting the JSON.\n"
                "After the </think> tag, YOU MUST OUTPUT ONLY VALID JSON with the following structure:\n"
                "{\n"
                '  "action": "move" | "ignore",\n'
                '  "destination_subfolder": "name of the existing folder to move into"\n'
                "}\n"
            )
            
            user_msg = (
                f"### User Rules / Prompt:\n{rules_prompt}\n\n"
                f"### Current File to Process:\nName: {os.path.basename(filepath)}\n"
                f"Content/Preview:\n{content_preview}\n"
            )
            
            messages = [{"role": "system", "content": sys_prompt}]
            user_payload = {"role": "user", "content": user_msg}
            if image_payloads:
                user_payload["images"] = image_payloads
            messages.append(user_payload)
            
            # Wipe context: no chat history!
            response = agent.client.chat(
                messages=messages,
                stream=True,
                temperature=0.0
            )
            
            raw_text = ""
            in_think = False
            ui_callback("🤔 ")
            
            for chunk in response:
                content = chunk.get("message", {}).get("content", "")
                if not content:
                    continue
                raw_text += content
                
                if "<think>" in raw_text and not in_think:
                    in_think = True
                    content = content.split("<think>")[-1]
                    
                if in_think:
                    if "</think>" in content:
                        clean_content = content.split("</think>")[0]
                        ui_callback(clean_content + "\n")
                        in_think = False
                    else:
                        clean_content = content.replace("<think>", "")
                        ui_callback(clean_content)
            
            # Extract json block
            json_str = raw_text
            if "```json" in raw_text:
                json_str = raw_text.split("```json")[1].split("```")[0]
            elif "```" in raw_text:
                json_str = raw_text.split("```")[1].split("```")[0]
            elif "</think>" in raw_text:
                json_str = raw_text.split("</think>")[1]
                
            data = json.loads(json_str.strip())
            
            action = data.get("action", "ignore")
            dest_folder = data.get("destination_subfolder", "").strip()
                
            if action == "move" and dest_folder:
                target_dir = os.path.join(output_dir, dest_folder)
                os.makedirs(target_dir, exist_ok=True)
                target_path = os.path.join(target_dir, os.path.basename(filepath))
                shutil.copy2(filepath, target_path)
                ui_callback(f"✅ Copied to {dest_folder}/\n")
            else:
                ui_callback("⏭️ Ignored\n")
                
            processed_count += 1
            
        except Exception as e:
            ui_callback(f"❌ Error: {str(e)}\n{traceback.format_exc()}\n")
            error_count += 1
            
    ui_callback("\n🎉 Data Processing Complete!\n")
    ui_callback(f"📊 Summary:\n- Processed: {processed_count}\n- Errors: {error_count}\n")
