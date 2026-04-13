# detect_model.py - Automatically finds working model name
import requests
import json

def list_models():
    """List all available models from LM Studio"""
    try:
        response = requests.get("http://localhost:1234/v1/models", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print("✅ Models found:")
            for model in data.get("data", []):
                print(f"  • {model['id']}")
            return data
        else:
            print(f"[ERROR] HTTP Status: {response.status_code}")
            print(response.text[:500])
            return None
    except Exception as e:
        print(f"[ERROR] Connection failed: {e}")
        return None

def test_chat(model_name, prompt="Explain quantum entanglement in one sentence."):
    """Test if a model works with chat completion"""
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 128,
        "stream": False
    }
    
    response = requests.post(
        "http://localhost:1234/v1/chat/completions",
        json=payload,
        headers={"Content-Type": "application/json"},
        timeout=60
    )
    
    if response.status_code == 200:
        result = response.json()
        
        if "choices" in result and len(result["choices"]) > 0:
            content = result["choices"][0]["message"]["content"]
            
            # Extract first few words for display
            preview = content[:100].replace('\n', ' ') + ("..." if len(content) > 100 else "")
            
            print(f"✅ {model_name} WORKS!")
            print(f"   Preview: {preview}")
            print(f"   Full length: {len(content)} characters")
            return content
        else:
            print(f"⚠️  Empty response from model {model_name}")
            if "error" in result:
                print(f"   Error: {result['error']}")
            else:
                print(f"   Debug: keys = {list(result.keys())}")
            return ""
    else:
        print(f"[ERROR] HTTP Status: {response.status_code} for model {model_name}")
        print(response.text[:200])
        return "Error"

# Run detection
print("=" * 60)
print("🔍 Model Name Detection")
print("=" * 60)

models = list_models()

if models:
    model_names = [m["id"] for m in models["data"]]
    print(f"\nFound {len(model_names)} models. Testing each...")
    
    success_count = 0
    working_model = None
    
    for model_name in model_names:
        # Clean up the model name (remove common prefixes/suffixes)
        clean_name = model_name.replace("/qwen", "").strip()
        
        result = test_chat(clean_name)
        if result and len(result.strip()) > 0 and "Error" not in result:
            success_count += 1
            working_model = clean_name
            print(f"\n🎯 WORKING MODEL FOUND: {clean_name}")
            break
    
    if not working_model:
        print("\n❌ No models responded with content")
        print("This might be a configuration issue. Check LM Studio logs.")
else:
    print("No models found. Are you sure the model is loaded?")
    print("Go to LM Studio → Developer tab → Loaded Models section")
