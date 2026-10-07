# Panda Helios — Theme Safety Reference

Use this reference only for theme/desktop work.

## Known-good graphics mode

- Session: KDE Plasma Wayland.
- Kernel: `linux-cachyos-lts`.
- Active graphics: Intel HD 630 using `i915`.
- NVIDIA proprietary modules are hard-blocked in safe/dev mode.
- Current safe boots show no NVIDIA Xids.
- Vulkan on Intel HD 630 is healthy and exposes Vulkan 1.4.

## Known visual limitation

On the current Helios, translucent/transparent desktop chrome has shown repaint artifacts:

- cursor trails were observed on Wayland with some GPU-rendered terminal chrome,
- translucent Konsole/titlebar surfaces could briefly flash previous application content,
- opaque Ghostty surfaces behaved better.

Design consequence:

- opaque-first is mandatory for v1,
- blur/transparency are optional capabilities for future hardware, not visual requirements,
- do not treat an opaque surface as a downgrade; it is part of the Helios capability profile.

## Forbidden incidental changes

Theme work must not modify:

- `/etc/default/limine`,
- kernel command lines,
- NVIDIA blacklist/isolation policy,
- sleep/suspend masks,
- disk partitions,
- filesystems,
- storage policy.

If a visual feature appears to require changes in those areas, stop and report the conflict.
