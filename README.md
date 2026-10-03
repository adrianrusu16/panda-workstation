# Panda Workstation

Reproducible CachyOS/Linux workstation configuration for Adrian.

## Goals

- Keep the workstation clean, fast, and reproducible
- Recreate the environment on future machines
- Separate portable configuration from hardware-specific configuration
- Support Linux, Android, Kotlin, C++, Rust, AOSP, and gaming workflows
- Keep credentials and secrets outside the repository

## Machines

- `panda-helios` — Acer Predator Helios 300
- `amd-desktop` — planned AMD desktop workstation

## Package layers

- `core.txt` — essential command-line tooling
- `desktop.txt` — desktop/session integration
- `development.txt` — general development tooling
- `android.txt` — Android and Kotlin development
- `aosp.txt` — AOSP build dependencies
- `gaming.txt` — gaming stack
- `panda.txt` — visual customization
