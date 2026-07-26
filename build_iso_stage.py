import os
import shutil
import sys

# Paths (change if different on your machine)
SOURCE_DIR = os.path.dirname(os.path.abspath(__file__))
ISO_BUILD_DIR = r"D:\citadel_os_ISO"
TARGET_DIR = os.path.join(ISO_BUILD_DIR, "airootfs", "usr", "share", "citadel")

# Lists of files and folders to transfer
INCLUDE_PATHS = ["core", "system", "apps", "main.py", "main_handlers.py", "config.py", "requirements.txt"]

def clean_pycache(target):
    """Removes compiled __pycache__ files from the target directory."""
    for root, dirs, files in os.walk(target):
        if "__pycache__" in dirs:
            pycache_path = os.path.join(root, "__pycache__")
            shutil.rmtree(pycache_path)

def main():
    print("[*] Starting preparation of Citadel source code for ISO...")

    if not os.path.exists(ISO_BUILD_DIR):
        print(f"[!] Error: Build directory {ISO_BUILD_DIR} not found.")
        sys.exit(1)

    # Clear the previous source build, if any
    if os.path.exists(TARGET_DIR):
        print("[*] Cleaning old sources in target...")
        shutil.rmtree(TARGET_DIR)

    os.makedirs(TARGET_DIR, exist_ok=True)

    # Copy the structure
    for path_name in INCLUDE_PATHS:
        src_path = os.path.join(SOURCE_DIR, path_name)
        dst_path = os.path.join(TARGET_DIR, path_name)

        if not os.path.exists(src_path):
            print(f"[?] Skipping: {path_name} not found in source.")
            continue

        print(f"[+] Copying: {path_name} -> ISO rootfs")
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)

    # Clean up dev clutter
    clean_pycache(TARGET_DIR)

    # Make sure no local logs or configs end up in the ISO, so we don't carry other people's passwords
    for private_file in ["citadel.log", "user_config.json"]:
        private_path = os.path.join(TARGET_DIR, "system", private_file)
        if os.path.exists(private_path):
            os.remove(private_path)
            print(f"[-] Removed local data file: {private_file}")

    print(f"\n[Stats] Build prepared successfully!")
    print(f"Citadel source code isolated in: {TARGET_DIR}")
    print("You can now move the D:\\citadel_os_ISO folder to an Arch Linux machine to run mkarchiso.")

if __name__ == "__main__":
    main()
