import os
import subprocess


def handle_files(intent):
    action = intent.get("action", "")
    path = intent.get("path", "")
    new_name = intent.get("new_name", "")
    is_folder = intent.get("is_folder", False)  # True = folder, False = file

    # ---------- CREATE ----------
    if action == "create":
        try:
            if is_folder:
                os.makedirs(path, exist_ok=True)
                return "Folder created"
            else:
                open(path, "w").close()
                return "File created"
        except Exception as e:
            return f"Failed to create {'folder' if is_folder else 'file'}: {e}"

    # ---------- DELETE ----------
    if action == "delete":
        try:
            if is_folder:
                import shutil
                shutil.rmtree(path)
                return "Folder deleted"
            else:
                os.remove(path)
                return "File deleted"
        except Exception as e:
            return f"Failed to delete {'folder' if is_folder else 'file'}: {e}"

    # ---------- RENAME ----------
    if action == "rename":
        try:
            os.rename(path, new_name)
            return f"{'Folder' if is_folder else 'File'} renamed"
        except Exception as e:
            return f"Rename failed: {e}"

    # ---------- OPEN ----------
    if action == "open":
        try:
            if is_folder:
                subprocess.Popen(["explorer", path])
                return "Folder opened"
            else:
                subprocess.Popen(["notepad", path])
                return "File opened"
        except Exception as e:
            return f"Cannot open {'folder' if is_folder else 'file'}: {e}"

    # ---------- SAVE CONTENT (files only) ----------
    if action == "save":
        if is_folder:
            return "Cannot save content to a folder"
        content = intent.get("content", "")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return "File saved"
        except Exception as e:
            return f"Save failed: {e}"

    # ---------- LIST FOLDER CONTENTS ----------
    if action == "list":
        if not is_folder:
            return "List action is only for folders"
        try:
            items = os.listdir(path)
            if not items:
                return "Folder is empty"
            result = []
            for item in items:
                full = os.path.join(path, item)
                kind = "📁" if os.path.isdir(full) else "📄"
                result.append(f"{kind} {item}")
            return "\n".join(result)
        except Exception as e:
            return f"Failed to list folder: {e}"

    return "Unknown command"