# Software Engineer AI Agent (AgentSWE)

**An autonomous local AI agent that writes, executes, and self-debugs Python code.**

![License](https://img.shields.io/badge/license-MIT-blue.svg) ![Python](https://img.shields.io/badge/python-3.10%2B-yellow.svg) ![Model](https://img.shields.io/badge/Model-Qwen2.5--Coder-violet.svg)

## 📖 Overview

AgentSWE is a **Level 2 AI Agent** operating in a closed feedback loop. It doesn't just generate code; it assumes responsibility for the execution environment.

1.  **Drafts** Python code using `qwen2.5-coder:7b`.
2.  **Executes** the code locally.
3.  **Heals the Environment:** Automatically runs `pip install` if a library is missing.
4.  **Debugs Logic:** If the code crashes, it feeds the stack trace back to the LLM to rewrite the script recursively.

## ⚡ Prerequisites

1.  **Ollama** installed (`brew install ollama` or via [ollama.com](https://ollama.com)).
2.  **Qwen 2.5 Coder** model pulled:
    ```bash
    ollama pull qwen2.5-coder:7b
    ```

## 🚀 Usage

1.  **Start the AI Backend:**
    ```bash
    ./start_ollama.sh
    ```

2.  **Run the Agent:**
    ```bash
    # Example: Stock Analysis (Triggers auto-install of yfinance)
    python3 agent.py "get the last 10 days of VOO stock prices and plot them"
    
    # Example: Web Scraping (Triggers self-debugging)
    python3 agent.py "scrape the top 5 headlines from Hacker News"
    ```

3.  **Stop the Backend:**
    ```bash
    ./stop_ollama.sh
    ```

## 🛠 Features
* **Auto-Pip:** Detects `ModuleNotFoundError` and installs packages on the fly.
* **Recursion:** Retries up to 4 times, learning from previous error logs.
* **Sanitization:** Cleans LLM hallucinations (like `pip install` commands inside Python scripts).

## 📄 License
MIT License. Free to use and modify.
