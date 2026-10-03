# 🐼 Panda Helios

## Hardware-specific notes

| Area | Status |
|---|:---:|
| Intel HD 630 | ✅ |
| NVIDIA GTX 1060 | ✅ |
| NVIDIA PRIME | ✅ |
| Wayland | ✅ |
| Plasma X11 fallback | ✅ |
| Suspend/resume | ⚠️ |

### Suspend

The laptop experienced an NVIDIA resume failure under Plasma Wayland.

Observed symptoms:

- black screen after resume
- TTY initially remained available
- NVIDIA driver reported Xid 158
- GPU reset was required

Actual suspend is temporarily disabled while the workstation is being stabilized.

Current sleep mode reported by the kernel:

```text
s2idle [deep]
```
