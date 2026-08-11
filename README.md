<div align="center">

# 🛡️ Citadel OS

### A released, full-featured Arch Linux distribution with the Hyprland desktop

[![Base](https://img.shields.io/badge/Base-Arch%20Linux-1793d1?logo=archlinux&logoColor=white)](https://archlinux.org/)
[![Desktop](https://img.shields.io/badge/Desktop-Hyprland-58e1ff)](https://hypr.land/)
[![Status](https://img.shields.io/badge/Status-Released-success)]()
[![Version](https://img.shields.io/badge/Version-3.0-orange)]()
[![License](https://img.shields.io/badge/License-MIT-green)]()

</div>

---

## About Citadel OS

**Citadel OS** is a released Linux operating system built on **Arch Linux**. It combines the Arch ecosystem with a fast, modern **Hyprland** graphical desktop and a focused set of built-in system, security, networking, and productivity tools.

Citadel OS is designed as a complete desktop environment—not as a standalone Python application. Its included utilities are part of the operating-system experience, while Arch Linux provides the foundation for package management, hardware support, and updates.

## Highlights

- **Arch Linux base** — access to `pacman`, the Arch package ecosystem, and a current rolling-release foundation.
- **Hyprland desktop** — a responsive Wayland compositor with a modern, keyboard-friendly workflow.
- **Live and rescue environment** — boot Citadel OS directly from its ISO for evaluation, maintenance, or recovery work.
- **System tools** — hardware overview, process and resource monitoring, storage inspection, logging, backups, and integrity checks.
- **Network tools** — interface information, local-network discovery, host reachability checks, and IP geolocation.
- **Security utilities** — local security auditing, authentication controls, encryption utilities, and password generation.
- **Everyday applications** — file browser, notes, weather, and an application launcher.

## Desktop environment

Citadel OS uses **Hyprland** as its graphical shell. The Wayland-based desktop is built for speed, flexibility, and efficient window management, while Citadel OS adds its own system utilities and visual identity around it.

## System components

| Area | Included capabilities |
|---|---|
| System management | Hardware information, process management, CPU/RAM monitoring, disk and memory usage |
| Networking | Interface configuration, network scanning, ping, and IP-based location tools |
| Security | Local audit tools, authentication, encrypted files and text, password generation |
| Recovery | Component integrity checks, backups, and session logging |
| Productivity | File browser, notes, weather, aliases, command history, and launcher |
| Packages | Native Arch Linux package management through `pacman` |

## Repository layout

```
citadel/
├── citadel_iso_build/    # ArchISO profile, package list, and live-system files
├── core/                 # Shell, session, command, and interface components
├── system/               # System, networking, recovery, and logging utilities
├── apps/                 # Built-in Citadel applications
├── modules/              # Desktop and environment modules
├── tests/                # Automated test suite
├── main.py               # Citadel session entry point
└── build_iso_stage.py    # ISO staging helper
```

## Building the ISO

The repository includes an ArchISO profile in `citadel_iso_build/`. Build the image on an Arch Linux system with the ArchISO tooling installed:

```bash
mkarchiso -v -w work -o out citadel_iso_build
```

The generated ISO can be written to a USB drive and booted on supported x86_64 hardware. Test it in a virtual machine before installing it on a physical system.

## Development and testing

Citadel OS includes automated tests for its internal tools and shell components:

```bash
pytest
```

## License

Citadel OS is distributed under the **MIT License**. You may use, modify, and distribute the source code, including for commercial purposes, subject to the license terms.

<div align="center">

Made with 🛡️ by the Citadel OS team

</div>
