import os
import sys
import asyncio
import subprocess
import datetime
import re
from textwrap import dedent
from typing import Optional, List, Dict

# Ollama Integration
try:
    from openai import AsyncOpenAI
except ImportError:
    raise ImportError("Please install openai SDK: pip install openai")

# IDE Manager Imports
try:
    from ide_manager import detect_installed_ides, detect_running_ide, launch_ide, open_file_in_ide
except ImportError:
    def detect_installed_ides():
        return []


    def detect_running_ide():
        return None


    def launch_ide(ide_name):
        pass


    def open_file_in_ide(filepath, ide_name=None):
        pass

# ────────────────────────────────────────────────
# CONFIGURATION & SECURITY
# ────────────────────────────────────────────────
SAVE_FOLDER = os.path.join(os.path.expanduser("~"), "Desktop", "HeartCode")
os.makedirs(SAVE_FOLDER, exist_ok=True)

llm_client = AsyncOpenAI(
    base_url="http://127.0.0.1:11434/v1",
    api_key="ollama"
)

MODEL_NAME = "qwen2.5-coder:7b"

# Enhanced Security Patterns for CyberSec Context
DANGEROUS_PATTERNS = [
    r"os\.system\(", r"subprocess\.call\(", r"rm -rf\s+/",
    r"format\s+[A-Z]:", r"del\s+/f", r"shutdown",
    r"socket\.bind\(", r"http\.server", r"eval\(",
    r":\(\)\s*\{.*:;\}", r"mkfs\.", r"dd\s+if="  # Fork bomb & Disk wiping protection
]

LANG_CONFIG = {
    "python": {
        "ext": ".py",
        "run": ["python", "{file}"],
        "install": "pip install {pkg}",
        "check_req": r"# REQUIRE:\s*(.*)"
    },
    "javascript": {
        "ext": ".js",
        "run": ["node", "{file}"],
        "install": "npm install {pkg}",
        "check_req": r"// REQUIRE:\s*(.*)"
    },
    "bash": {
        "ext": ".sh",
        "run": ["bash", "{file}"],
        "install": "N/A",
        "header": "#!/bin/bash\nset -euo pipefail\n"  # Strict mode for security
    },
    "powershell": {
        "ext": ".ps1",
        "run": ["powershell", "-ExecutionPolicy", "Bypass", "-File", "{file}"]
    },
    "java": {
        "ext": ".java",
        "compile": ["javac", "{file}"],
        "run": ["java", "{name}"]
    },
    "c++": {
        "ext": ".cpp",
        "compile": ["g++", "{file}", "-o", "{name}.exe"],
        "run": ["{name}.exe"]
    },
    "go": {
        "ext": ".go",
        "run": ["go", "run", "{file}"],
        "install": "go get {pkg}"
    },
}


class HeartCodingAgent:
    def __init__(self):
        self.session_ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    def detect_language(self, text: str) -> str:
        t = text.lower()
        # Explicit checks for CyberSec terms
        if any(k in t for k in ["bash", "shell", "script", "nmap", "grep", "awk"]):
            return "bash"
        if any(k in t for k in ["python", "automation", "scrapy", "flask"]):
            return "python"

        scores = {lang: 0 for lang in LANG_CONFIG.keys()}
        keywords = {
            "python": ["def ", "import ", "print("],
            "javascript": ["console.log", "const ", "let "],
            "bash": ["#!/bin/bash", "echo $", "chmod", "ls -la", "curl"],
            "powershell": ["Get-ChildItem", "Write-Host"],
        }

        for lang, keys in keywords.items():
            for key in keys:
                if key in t: scores[lang] += 2

        best_lang = max(scores, key=scores.get)
        return best_lang if scores[best_lang] > 0 else "python"

    def is_safe_code(self, code: str, language: str) -> bool:
        for pattern in DANGEROUS_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return False
        # Extra check for Bash specific dangers
        if language == "bash" and ("sudo" in code or "root" in code):
            # Allow but warn, or block depending on strictness. For now, we allow but log.
            print("[Heart] Warning: Script contains elevated privileges.")
        return True

    async def generate_code(self, user_request: str, language: str) -> str:
        system_prompt = dedent(f"""\
            You are a Senior Cybersecurity Analyst and Software Architect specializing in {language}.
            TASK: Generate secure, efficient code for: "{user_request}"

            RULES:
            1. CODE ONLY: No markdown, no explanations.
            2. SECURITY: Sanitize inputs. Avoid dangerous system calls.
            3. BASH SPECIFIC: Always use 'set -euo pipefail' for robustness.
            4. DEPENDENCIES: Add '# REQUIRE: package_name' if needed.

            OUTPUT: Pure source code only.
        """)

        try:
            response = await llm_client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Generate code now."}
                ],
                temperature=0.1,
                max_tokens=4096
            )
            code = response.choices[0].message.content.strip()
            if code.startswith("```"):
                code = re.sub(r'^```[a-z]*\n', '', code)
                code = re.sub(r'\n```$', '', code)

            # Add Bash Header if missing
            if language == "bash" and not code.startswith("#!/bin/bash"):
                code = LANG_CONFIG["bash"]["header"] + code

            return code.strip()
        except Exception as e:
            return f"# ERROR: {str(e)}"

    async def install_dependencies(self, code: str, language: str) -> str:
        config = LANG_CONFIG.get(language)
        if not config or "check_req" not in config:
            return "OK"

        matches = re.findall(config["check_req"], code)
        if not matches: return "OK"

        pkg = matches[0].strip()
        cmd = config["install"].format(pkg=pkg).split()

        print(f"[Heart] Installing: {pkg}")
        try:
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            await proc.communicate()
            return f"Installed {pkg}" if proc.returncode == 0 else f"Failed {pkg}"
        except:
            return "Install Error"

    async def execute_code(self, filepath: str, language: str) -> Dict[str, str]:
        config = LANG_CONFIG.get(language.lower())
        if not config: return {"status": "error", "msg": "Unsupported"}

        filename = os.path.basename(filepath)
        name_without_ext = os.path.splitext(filename)[0]

        # Compilation for Java/C++
        if "compile" in config:
            cmd_compile = [p.format(file=filepath, name=name_without_ext) for p in config["compile"]]
            try:
                proc = await asyncio.create_subprocess_exec(*cmd_compile, stdout=subprocess.PIPE,
                                                            stderr=subprocess.PIPE)
                _, stderr = await proc.communicate()
                if proc.returncode != 0:
                    return {"status": "compile_error", "error": stderr.decode('utf-8', errors='ignore')}
            except Exception as e:
                return {"status": "crash", "msg": str(e)}

        # Execution
        cmd_run = [p.format(file=filepath, name=name_without_ext) for p in config["run"]]

        # Windows Bash Handling
        if language.lower() == "bash":
            if sys.platform.startswith("win"):
                # Try Git Bash or WSL if available, otherwise warn
                bash_path = os.environ.get("GIT_BASH", "C:\\Program Files\\Git\\bin\\bash.exe")
                if os.path.exists(bash_path):
                    cmd_run[0] = bash_path
                else:
                    return {"status": "warning", "msg": "Bash requires Git Bash or WSL on Windows."}

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd_run, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=os.path.dirname(filepath)
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15.0)

            output = stdout.decode('utf-8', errors='ignore').strip()
            errors = stderr.decode('utf-8', errors='ignore').strip()

            if proc.returncode == 0:
                return {"status": "success", "output": output}
            else:
                return {"status": "error", "error": errors}
        except asyncio.TimeoutError:
            return {"status": "timeout", "msg": "Timed out."}
        except FileNotFoundError:
            return {"status": "missing_runtime", "msg": f"{language} runtime missing."}

    async def self_heal(self, code: str, language: str, error_msg: str) -> str:
        fix_prompt = f"Fix this {language} code. Error: {error_msg}\nCode:\n{code}\nOutput ONLY fixed code."
        try:
            response = await llm_client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": fix_prompt}],
                temperature=0.1
            )
            fixed = response.choices[0].message.content.strip()
            if fixed.startswith("```"):
                fixed = re.sub(r'^```[a-z]*\n', '', fixed)
                fixed = re.sub(r'\n```$', '', fixed)
            if language == "bash" and not fixed.startswith("#!/bin/bash"):
                fixed = LANG_CONFIG["bash"]["header"] + fixed
            return fixed
        except:
            return code

    async def run(self, text: str, auto_run: bool = True, open_ide: bool = False) -> str:
        if not text.strip(): return "Koi instruction nahi mila."

        language = self.detect_language(text)
        print(f"[Heart] Target: {language}")

        code = await self.generate_code(text, language)
        if code.startswith("# ERROR"): return f"LLM Error: {code}"
        if not self.is_safe_code(code, language): return "🚫 Security Block."

        ts = datetime.datetime.now().strftime("%H%M%S")
        ext = LANG_CONFIG[language]["ext"]
        filename = f"Heart_{ts}{ext}"
        filepath = os.path.join(SAVE_FOLDER, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(code)

        dep_status = await self.install_dependencies(code, language)

        result_msg = ""
        if auto_run:
            res = await self.execute_code(filepath, language)
            if res["status"] == "error":
                print("[Heart] Healing...")
                fixed_code = await self.self_heal(code, language, res.get("error", ""))
                with open(filepath, "w", encoding="utf-8") as f: f.write(fixed_code)
                res = await self.execute_code(filepath, language)

            if res["status"] == "success":
                result_msg = f"✅ Output:\n{res['output']}"
            else:
                result_msg = f"⚠️ {res.get('msg', res.get('error', 'Failed'))}"

        ide_msg = ""
        if open_ide:
            running = detect_running_ide()
            installed = detect_installed_ides()
            target = running or (installed[0] if installed else None)
            if target:
                open_file_in_ide(filepath, target)
                ide_msg = f"🚀 Opened in {target}"

        return f" **{language.upper()}** Saved: `{filepath}`\n📦 Deps: {dep_status}\n{result_msg}\n{ide_msg}"

    async def handle_coding(self, text: str, auto_run: bool = True) -> str:
        return await self.run(text, auto_run=auto_run, open_ide=False)