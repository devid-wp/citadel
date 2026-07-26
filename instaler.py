import os
import subprocess
import time
import sys

# ANSI colors for the installer UI
PURPLE = "\033[95m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[31m"
RESET = "\033[0m"

def run_cmd(cmd, shell=True):
    """Helper to run system commands with status reporting."""
    try:
        result = subprocess.run(cmd, shell=shell, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def print_header():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{PURPLE}==================================================================={RESET}")
    print(f"{PURPLE}          CITADEL OS v1.0 (Core 3.0) - AUTOMATIC INSTALLER         {RESET}")
    print(f"{PURPLE}==================================================================={RESET}\n")

def main():
    print_header()
    print(f"[{YELLOW}WARNING{RESET}]: This script automates the installation of an Arch Linux core.")
    print("Make sure you are running it inside an Arch Linux Live-CD environment.\n")

    # 1. Disk selection
    print(f"{CYAN}[ STEP 1 ]: Detecting available storage devices...{RESET}")
    # List disks in Linux (lsblk)
    success, disks = run_cmd("lsblk -d -o NAME,SIZE,MODEL")
    if not success:
        print(f"{RED}Could not list disks. The script must run on Linux.{RESET}")
        sys.exit(1)

    print(disks)
    target_disk = input(f"Enter the target disk name for installation (e.g. {GREEN}sda{RESET} or {GREEN}nvme0n1{RESET}): ").strip()

    if not target_disk:
        print(f"{RED}No disk selected. Exiting.{RESET}")
        sys.exit(1)

    confirm = input(f"{RED}WARNING! All data on /dev/{target_disk} will be DESTROYED. Continue? (y/n): {RESET}").strip().lower()
    if confirm != 'y':
        print("Installation cancelled.")
        sys.exit(0)

    # 2. Automatic disk partitioning (EFI + Root)
    print(f"\n{CYAN}[ STEP 2 ]: Partitioning /dev/{target_disk} (GPT)...{RESET}")
    # Create a GPT table, 512MB for EFI, rest for root
    partition_cmds = f"""
    sgdisk --zap-all /dev/{target_disk}
    sgdisk --new=1:0:+512M --typecode=1:ef00 --change-name=1:EFI /dev/{target_disk}
    sgdisk --new=2:0:0 --typecode=2:8300 --change-name=2:ROOT /dev/{target_disk}
    """
    for cmd in partition_cmds.strip().split('\n'):
        if cmd.strip():
            run_cmd(cmd.strip())

    # Determine resulting partition names
    p_prefix = "p" if "nvme" in target_disk else ""
    efi_part = f"/dev/{target_disk}{p_prefix}1"
    root_part = f"/dev/{target_disk}{p_prefix}2"

    # 3. Filesystem formatting
    print(f"\n{CYAN}[ STEP 3 ]: Formatting partitions...{RESET}")
    print(f"-> Formatting {efi_part} as FAT32 (EFI)...")
    run_cmd(f"mkfs.fat -F32 {efi_part}")
    print(f"-> Formatting {root_part} as Ext4 (System)...")
    run_cmd(f"mkfs.ext4 -F {root_part}")

    # 4. Mounting partitions for installation
    print(f"\n{CYAN}[ STEP 4 ]: Mounting the file structure...{RESET}")
    run_cmd(f"mount {root_part} /mnt")
    run_cmd("mkdir -p /mnt/boot")
    run_cmd(f"mount {efi_part} /mnt/boot")

    # 5. Install base Arch Linux packages (Pacstrap)
    print(f"\n{CYAN}[ STEP 5 ]: Deploying core base packages (Pacstrap)...{RESET}")
    print("This will take a while, Linux components are downloading...")
    # Install base system, kernel, firmware, a text editor, and Python for our shell
    success, out = run_cmd("pacstrap -K /mnt base linux linux-firmware base-devel python nano grub efibootmgr networkmanager")
    if not success:
        print(f"{RED}Pacstrap failed:{RESET}\n{out}")
        sys.exit(1)
    print(f"{GREEN}[Success]: Base packages installed.{RESET}")

    # 6. Generate fstab
    print(f"\n{CYAN}[ STEP 6 ]: Generating fstab...{RESET}")
    run_cmd("genfstab -U /mnt >> /mnt/etc/fstab")

    # 7. Configure the system inside chroot (base configuration)
    print(f"\n{CYAN}[ STEP 7 ]: Internal Citadel OS configuration...{RESET}")

    # Configuration script that runs inside the installed system
    chroot_script = f"""
    ln -sf /usr/share/zoneinfo/UTC /etc/localtime
    hwclock --systohc
    echo "en_US.UTF-8 UTF-8" > /etc/locale.gen
    locale-gen
    echo "LANG=en_US.UTF-8" > /etc/locale.conf
    echo "citadel-node" > /etc/hostname
    echo "127.0.0.1 localhost" >> /etc/hosts
    echo "::1       localhost" >> /etc/hosts
    systemctl enable NetworkManager

    # Configure GUKB bootloader
    grub-install --target=x86_64-efi --efi-directory=/boot --bootloader-id=CITADEL-BOOT
    grub-mkconfig -o /boot/grub/grub.cfg

    # Set default root password: admin
    echo "root:admin" | chpasswd
    """

    with open("/mnt/chroot_setup.sh", "w") as f:
        f.write(chroot_script)

    run_cmd("arch-chroot /mnt bash /chroot_setup.sh")
    run_cmd("rm /mnt/chroot_setup.sh")

    # 8. Integrate the Citadel OS interface as the main shell
    print(f"\n{CYAN}[ STEP 8 ]: Integrating the Citadel shell interface...{RESET}")

    # Create the folder for our system inside the installed disk.
    # Production path: /opt/citadel/ (hardcoded — run as root).
    target_os_dir = "/mnt/opt/citadel"
    run_cmd(f"mkdir -p {target_os_dir}")

    # Copy our project files (main.py, config.py, logo.txt and the core/system/apps folders).
    # Assumes the installer is run from the folder containing these files.
    # Live-CD paths are absolute.
    run_cmd(f"cp -r main.py config.py logo.txt core system apps {target_os_dir}/ 2>/dev/null")

    # Configure autostart of our Python shell on login instead of the default bash.
    # In production /opt/citadel/main.py — absolute path, python3 lives in /usr/bin/.
    bashprofile_path = "/mnt/root/.bash_profile"
    autorun_code = f"""
    # Autostart for Citadel OS v1.0 (Core 3.0) interface
    if [ -f /opt/citadel/main.py ]; then
        exec /usr/bin/python3 /opt/citadel/main.py
        # If the user exits our shell, also end the terminal session itself
        exit
    fi
    """
    with open(bashprofile_path, "w") as f:
        f.write(autorun_code)

    # 9. Final
    print(f"\n{GREEN}==================================================================={RESET}")
    print(f"{GREEN}          CITADEL OS SUCCESSFULLY INSTALLED ON YOUR PC!             {RESET}")
    print(f"{GREEN}==================================================================={RESET}")
    print("You can remove the installation media and reboot the computer.\n")

if __name__ == "__main__":
    # Simple check: if run on Windows, the script warns but does not break
    if os.name == 'nt':
        print_header()
        print(f"[{YELLOW}DEBUG{RESET}]: Installer code parses correctly.")
        print("For a real installation, this file must be run inside an Arch Linux Live-CD.")
    else:
        main()
