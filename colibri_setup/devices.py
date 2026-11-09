"""Cross-platform device detection for the Colibri installer/setup.

Detects OS, arch, CPU/RAM, GPU (NVIDIA CUDA + Vulkan), Intel NPU (OpenVINO), and
free disk on the model/cache drive. Degrades gracefully when a probe is missing
so it runs on Windows, macOS and Linux alike. Pure stdlib + optional probes.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field, asdict


def _run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


@dataclass
class Device:
    os: str = ""
    os_version: str = ""
    arch: str = ""
    cpu_cores: int = 0
    ram_gb: float = 0.0
    gpu: list = field(default_factory=list)
    npu: bool = False
    cuda: bool = False
    vulkan: bool = False
    disk_free_gb: float = 0.0
    disk_path: str = ""
    python: str = ""
    tier: str = "cpu"

    def to_dict(self):
        return asdict(self)


def _ram_gb():
    sys = platform.system()
    if sys == "Windows":
        out = _run(["wmic", "ComputerSystem", "get", "TotalPhysicalMemory"])
        for line in out.splitlines():
            line = line.strip()
            if line.isdigit():
                return round(int(line) / 1024**3, 1)
        try:
            import ctypes
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return round(stat.ullTotalPhys / 1024**3, 1)
        except Exception:
            return 0.0
    if sys == "Darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        return round(int(out) / 1024**3, 1) if out.isdigit() else 0.0
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return round(int(line.split()[1]) / 1024**2, 1)
    except Exception:
        pass
    return 0.0


def _nvidia_gpus():
    out = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    gpus = []
    for line in out.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            try:
                gpus.append({"name": parts[0], "vram_mb": int(parts[1]), "kind": "nvidia"})
            except ValueError:
                gpus.append({"name": parts[0], "vram_mb": 0, "kind": "nvidia"})
    return gpus


def _has_cuda():
    try:
        import torch
        return bool(torch.cuda.is_available())
    except Exception:
        return bool(_run(["nvidia-smi", "-L"]))


def _has_vulkan():
    sys = platform.system()
    if sys == "Windows":
        return bool(_run(["where", "vulkaninfo"])) or os.path.exists(
            os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "vulkan-1.dll"))
    return bool(shutil.which("vulkaninfo"))


def _has_intel_npu():
    try:
        import openvino as ov
        core = ov.Core()
        return any("NPU" in d.upper() for d in core.available_devices)
    except Exception:
        return False


def detect(disk_path=None):
    sys = platform.system()
    disk_path = disk_path or ("D:/" if sys == "Windows" and os.path.exists("D:/") else os.path.expanduser("~"))
    gpus = _nvidia_gpus()
    cuda = _has_cuda()
    vulkan = _has_vulkan()
    npu = _has_intel_npu()
    try:
        free = shutil.disk_usage(disk_path).free / 1024**3
    except Exception:
        free = 0.0
    if cuda and gpus:
        tier = "cuda"
    elif vulkan and gpus:
        tier = "vulkan"
    elif npu:
        tier = "npu"
    else:
        tier = "cpu"
    return Device(
        os=sys, os_version=platform.release(), arch=platform.machine(),
        cpu_cores=os.cpu_count() or 0, ram_gb=_ram_gb(), gpu=gpus, npu=npu,
        cuda=cuda, vulkan=vulkan, disk_free_gb=round(free, 1), disk_path=disk_path,
        python=platform.python_version(), tier=tier,
    )


def recommend(dev: Device):
    """Suggest a context window + tier policy from detected hardware."""
    vram = max((g.get("vram_mb", 0) for g in dev.gpu), default=0) / 1024
    if dev.tier in ("cuda", "vulkan") and vram >= 7.5 and dev.ram_gb >= 16:
        return {"policy": "quality", "ctx": 32768, "auto_tier": True,
                "note": "GPU hot tier + host pool; large context."}
    if dev.tier == "npu":
        return {"policy": "balanced", "ctx": 8192, "auto_tier": True,
                "note": "NPU embeddings; CPU/iGPU inference."}
    return {"policy": "balanced", "ctx": 8192, "auto_tier": True,
            "note": "CPU inference; consider a smaller model."}


if __name__ == "__main__":
    import json
    d = detect()
    print(json.dumps({"device": d.to_dict(), "recommendation": recommend(d)}, indent=2))