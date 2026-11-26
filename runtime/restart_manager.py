import os
import sys
import subprocess
import gc


def graceful_restart():
    """Fixed Restart - Handles spaces in username properly"""
    print("[HEART] Restarting process with full cleanup...")

    try:
        # Memory cleanup before restart
        gc.collect(2)

        # Clear Torch GPU cache if available
        if 'torch' in sys.modules:
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    print("[GPU] VRAM cleared before restart")
            except:
                pass

        python_exe = sys.executable
        script_path = os.path.abspath(sys.argv[0])

        print(f"[HEART] Restarting: {python_exe} \"{script_path}\"")

        # Best method: Use subprocess (handles spaces safely)
        subprocess.Popen([python_exe, script_path] + sys.argv[1:])

        # Exit current process cleanly
        sys.exit(0)

    except Exception as e:
        print(f"[RESTART ERROR] {e}")
        print("Trying fallback method...")
        try:
            # Fallback to os.execv
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except:
            sys.exit(0)