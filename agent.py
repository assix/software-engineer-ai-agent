import requests
import json
import sys
import os
import time
import subprocess
import re
import signal
import atexit

# Configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
CHECK_URL = "http://localhost:11434/"
MODEL = "qwen2.5-coder:7b"
OLLAMA_PROCESS = None

def slugify(text):
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', text).lower()
    slug = re.sub(r'\s+', '_', clean)
    return slug[:50]

def cleanup_ollama():
    """Kills the background Ollama process if we started it."""
    global OLLAMA_PROCESS
    if OLLAMA_PROCESS:
        print("\n💤 Stopping Ollama to save RAM...")
        OLLAMA_PROCESS.terminate()
        try:
            OLLAMA_PROCESS.wait(timeout=3)
        except subprocess.TimeoutExpired:
            OLLAMA_PROCESS.kill()
        print("   Ollama stopped.")

def ensure_ollama_running():
    """Checks if Ollama is running; if not, starts it temporarily."""
    global OLLAMA_PROCESS
    try:
        requests.get(CHECK_URL, timeout=0.5)
        # If request succeeds, it's already running. We do NOT touch it.
        return
    except requests.exceptions.ConnectionError:
        print("🚀 Starting Ollama (On-Demand)...")
        try:
            # Start ollama serve in background, hiding logs
            OLLAMA_PROCESS = subprocess.Popen(
                ["ollama", "serve"], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            # Register cleanup to run on exit
            atexit.register(cleanup_ollama)
            
            # Wait for it to be ready
            retries = 0
            while retries < 20:
                try:
                    requests.get(CHECK_URL, timeout=0.5)
                    print("   Ollama is ready.")
                    return
                except:
                    time.sleep(1)
                    print(f"   Waiting for AI engine... ({retries+1}/20)")
                    retries += 1
            print("❌ Error: Ollama failed to start.")
            sys.exit(1)
        except FileNotFoundError:
            print("❌ Error: 'ollama' command not found. Run: brew install ollama")
            sys.exit(1)

def sanitize_code(code):
    lines = code.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(("pip install", "python ", "python3 ")): continue
        if stripped.lower().startswith(("here is", "sure,", "to run")): continue
        if line.startswith("return "): line = f"print({line[7:]})"
        cleaned_lines.append(line)
    
    code = '\n'.join(cleaned_lines)
    replacements = {
        "beautiful_soup": "BeautifulSoup",
        "date_time": "datetime",
        "from bs4 import bs4": "import bs4"
    }
    for bad, good in replacements.items():
        code = code.replace(bad, good)
    return code

def fix_imports(code):
    common_libs = {
        "requests.": "import requests",
        "json.": "import json",
        "sys.": "import sys",
        "os.": "import os",
        "pd.": "import pandas as pd",
        "np.": "import numpy as np",
        "BeautifulSoup": "from bs4 import BeautifulSoup",
        "yf.": "import yfinance as yf"
    }
    injections = [stmt for kw, stmt in common_libs.items() if kw in code and stmt not in code]
    if injections:
        return "\n".join(injections) + "\n\n" + code
    return code

def query_llm(prompt):
    ensure_ollama_running() # Ensure engine is up before asking
    payload = {"model": MODEL, "prompt": prompt, "stream": False}
    try:
        response = requests.post(OLLAMA_URL, json=payload)
        response.raise_for_status()
        raw = response.json().get("response", "")
        match = re.search(r"```(?:python)?(.*?)```", raw, re.DOTALL)
        return match.group(1).strip() if match else raw.strip()
    except Exception as e:
        print(f"LLM Error: {e}")
        sys.exit(1)

def get_code(nlp_prompt, error_context=None, broken_code=None):
    if error_context:
        print(f"#> 🧠 DEBUGGING: Asking {MODEL} to fix the bug...")
        system_prompt = (
            f"You are a Senior Python Engineer. The following script failed to run.\n"
            f"TASK: {nlp_prompt}\n\n"
            f"--- BROKEN CODE ---\n{broken_code}\n\n"
            f"--- ERROR LOG ---\n{error_context}\n\n"
            f"INSTRUCTIONS: Rewrite the code to fix the error. Return ONLY the valid Python code block."
        )
    else:
        print(f"#> 🎨 CREATING: Asking {MODEL} to write the script...")
        system_prompt = (
            f"Write a Python script to {nlp_prompt}. "
            "Rules: Return ONLY valid Python code. No functions (flat script). "
            "Do NOT use 'pip install'. Use standard libraries where possible."
        )

    raw_code = query_llm(system_prompt)
    code = sanitize_code(raw_code)
    code = fix_imports(code)
    return code

def install_package(package_name):
    print(f"    [+] Installing missing library: {package_name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

def run_agent_loop(prompt):
    slug = slugify(prompt)
    filename = f"generated_{slug}.py"
    
    code = get_code(prompt)
    
    max_retries = 4
    for attempt in range(max_retries):
        header = f"# TASK: {prompt}\n# MODE: {'Auto-Debugged' if attempt > 0 else 'Generated'}\n"
        with open(filename, "w") as f: f.write(header + code)
        
        if attempt == 0:
            print(f"\n#> SCRIPT: {filename}")
            print("="*60)

        try:
            result = subprocess.run([sys.executable, filename], check=True, capture_output=True, text=True)
            print(result.stdout)
            print(f"\n✅ Success on attempt {attempt+1}!")
            return True

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr or e.stdout or "Unknown Error"
            import_match = re.search(r"ModuleNotFoundError: No module named '(.*?)'", error_msg)
            if import_match:
                pkg = import_match.group(1)
                if pkg == "bs4": pkg = "beautifulsoup4"
                if pkg == "sklearn": pkg = "scikit-learn"
                
                print(f"    [!] Missing Module: {pkg}")
                if install_package(pkg):
                    print("    [R] Retrying with new package...")
                    continue 
            
            print(f"    [!] Logic Error detected on attempt {attempt+1}:")
            print(f"        {error_msg.strip().splitlines()[-1]}")
            
            if attempt < max_retries - 1:
                code = get_code(prompt, error_context=error_msg, broken_code=code)
            else:
                print("\n❌ Failed after max retries.")
                print("-" * 20 + " FULL ERROR LOG " + "-" * 20)
                print(error_msg)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 agent.py 'prompt'")
        sys.exit(1)
    run_agent_loop(sys.argv[1])
