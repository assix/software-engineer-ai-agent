import requests
import json
import sys
import os
import time
import subprocess
import re
import atexit
import platform

# ------------------------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
CHECK_URL = "http://localhost:11434/"
MODEL = "qwen2.5-coder:7b"
OLLAMA_PROCESS = None

# ------------------------------------------------------------------------------
# SYSTEM OPERATIONS
# ------------------------------------------------------------------------------
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
        return
    except requests.exceptions.ConnectionError:
        print("🚀 Starting Ollama (On-Demand)...")
        try:
            OLLAMA_PROCESS = subprocess.Popen(
                ["ollama", "serve"], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
            atexit.register(cleanup_ollama)
            for _ in range(20):
                try:
                    requests.get(CHECK_URL, timeout=0.5)
                    print("   Ollama is ready.")
                    return
                except:
                    time.sleep(1)
            print("❌ Error: Ollama failed to start.")
            sys.exit(1)
        except FileNotFoundError:
            print("❌ Error: 'ollama' command not found. Install it first.")
            sys.exit(1)

def install_system_package(pkg_name):
    """
    Handles non-pip system packages (like tkinter) based on OS.
    """
    system = platform.system().lower()
    
    # 1. Define the command based on OS
    if system == "linux":
        # DGX / Ubuntu / Debian
        print(f"    [🐧] Detected Linux. Attempting apt install for '{pkg_name}'...")
        if pkg_name == "tkinter":
            cmd = ["sudo", "apt-get", "install", "-y", "python3-tk"]
        else:
            return False # We don't know the apt name for other random pkgs
            
    elif system == "darwin":
        # macOS
        print(f"    [🍎] Detected macOS. Attempting brew install for '{pkg_name}'...")
        if pkg_name == "tkinter":
            cmd = ["brew", "install", "python-tk"]
        else:
            return False
            
    else:
        print(f"    [?] Unknown OS: {system}. Cannot install system packages automatically.")
        return False

    # 2. Try to run it
    try:
        subprocess.check_call(cmd)
        print("    [✅] System package installed successfully.")
        return True
    except subprocess.CalledProcessError:
        print(f"    [❌] Failed to install '{pkg_name}'. You likely need sudo/root permissions.")
        print(f"         Run this manually: {' '.join(cmd)}")
        return False
    except FileNotFoundError:
        print(f"    [❌] Package manager not found (tried: {cmd[0]}).")
        return False

def install_package(package_name):
    # Special handling for Tkinter (Not a pip package)
    if package_name == "tkinter":
        return install_system_package("tkinter")

    print(f"    [+] Installing missing library via pip: {package_name}...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package_name], 
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except:
        return False

# ------------------------------------------------------------------------------
# AI LOGIC
# ------------------------------------------------------------------------------
def slugify(text):
    clean = re.sub(r'[^a-zA-Z0-9\s]', '', text).lower()
    return re.sub(r'\s+', '_', clean)[:50]

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
    # Typo fixes
    code = code.replace("beautiful_soup", "BeautifulSoup")
    code = code.replace("from bs4 import bs4", "import bs4")
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
    ensure_ollama_running() 
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
            result = subprocess.run(
                [sys.executable, filename], 
                check=True, 
                text=True, 
                stdout=None,       # Inherit (Print to screen immediately)
                stderr=subprocess.PIPE # Capture errors silently for Self-Healing
            )
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
                print(error_msg)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 agent.py 'prompt'")
        sys.exit(1)
    run_agent_loop(sys.argv[1])
