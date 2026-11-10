"""Cross-platform device detection for the Colibri installer/setup.

Detects OS, arch, CPU/RAM, GPU (NVIDIA CUDA + Vulkan), Intel NPU (OpenVINO), and
free disk on the model/cache drive. Degrades gracefully when a probe is missing
so it runs on Windows, macOS and Linux alike. Pure stdlib + optional probes.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path
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
    metal: bool = False
    client_only: bool = False
    termux: bool = False
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


def _vulkan_gpus():
    output = _run(["vulkaninfo", "--summary"])
    devices = []
    for block in re.split(r"(?m)^\s*GPU\d+:?\s*$", output)[1:]:
        match = re.search(r"deviceName\s*=\s*([^\r\n]+)", block)
        if not match or "PHYSICAL_DEVICE_TYPE_CPU" in block:
            continue
        name = match.group(1).strip()
        if any(software in name.lower() for software in ("llvmpipe", "lavapipe", "swiftshader")):
            continue
        kind = next((vendor for vendor in ("nvidia", "amd", "intel") if vendor in name.lower()), "vulkan")
        if "radeon" in name.lower():
            kind = "amd"
        devices.append({"name": name, "vram_mb": 0, "kind": kind, "api": "vulkan"})
    return devices


def _metal_gpus():
    output = _run(["system_profiler", "SPDisplaysDataType", "-json"])
    try:
        displays = json.loads(output).get("SPDisplaysDataType", [])
    except (ValueError, AttributeError):
        displays = []
    devices = []
    for display in displays:
        metal = str(display.get("spdisplays_metal", display.get("spdisplays_metalFamily", "")))
        name = display.get("sppci_model", "")
        if name and metal and not any(word in metal.lower() for word in ("unsupported", "not supported")):
            devices.append({"name": name, "vram_mb": 0, "kind": "apple" if "Apple" in name else "metal", "api": "metal"})
    # Apple Silicon supports Metal, but shared system RAM is not dedicated VRAM.
    if not devices:
        brand = _run(["sysctl", "-n", "machdep.cpu.brand_string"])
        if brand.startswith("Apple ") and platform.machine().lower() in ("arm64", "aarch64"):
            devices.append({"name": brand, "vram_mb": 0, "kind": "apple", "api": "metal"})
    return devices


def _has_intel_npu():
    try:
        import openvino as ov
        core = ov.Core()
        return any("NPU" in d.upper() for d in core.available_devices)
    except Exception:
        return False


def detect(disk_path=None):
    system = platform.system()
    termux = "com.termux" in os.environ.get("PREFIX", "")
    if system == "Android" or hasattr(sys, "getandroidapilevel") or (os.environ.get("ANDROID_ROOT") and not termux):
        system = "Android"
    # Termux is a Linux userspace on the phone: it can host the core and PWA.
    client_only = system.lower() in ("android", "ios", "ipados") and not termux
    disk = Path(disk_path or Path.home()).expanduser()
    while not disk.exists() and disk != disk.parent:
        disk = disk.parent
    nvidia = [] if client_only else _nvidia_gpus()
    vk = [] if client_only else _vulkan_gpus()
    metal = _metal_gpus() if system == "Darwin" else []
    gpus = list(nvidia)
    for gpu in vk + metal:
        existing = next((g for g in gpus if g["name"].casefold() == gpu["name"].casefold()), None)
        if existing:
            existing["api"] = gpu["api"]
        else:
            gpus.append(gpu)
    npu = False if client_only else _has_intel_npu()
    try:
        free = shutil.disk_usage(disk).free / 1024**3
    except OSError:
        free = 0.0
    tier = "client" if client_only else "cuda" if nvidia else "metal" if metal else "vulkan" if vk else "cpu"
    return Device(
        os=system, os_version=platform.release(), arch=platform.machine(),
        cpu_cores=os.cpu_count() or 0, ram_gb=_ram_gb(), gpu=gpus, npu=npu,
        cuda=bool(nvidia), vulkan=bool(vk), metal=bool(metal), client_only=client_only,
        termux=termux, disk_free_gb=round(free, 1), disk_path=str(disk),
        python=platform.python_version(), tier=tier,
    )


def recommend(dev: Device):
    """Hardware visibility is not proof that a native backend was compiled."""
    vram = max((g.get("vram_mb", 0) for g in dev.gpu), default=0) / 1024
    ctx = 2048
    if vram >= 8 and dev.ram_gb >= 16:
        ctx = 4096
    if vram >= 24 and dev.ram_gb >= 64:
        ctx = 8192
    note = "Conservative starting context; model size/KV cache must fit. Native accelerator support is unverified; default CPU."
    if dev.npu:
        note += " NPU is an embedding sidecar only, not a decoder."
    if dev.client_only:
        note = "Android/iOS: PWA client only. Run the shared agent and engine on a Windows/macOS/Linux host."
    elif dev.termux:
        note = ("Termux on Android: the local core and PWA run on this phone. "
                "On-device engine inference needs a compatible small model and an unverified ARM build; "
                "the 35B model does not fit.")
    return {"backend": "cpu", "candidate_backend": dev.tier, "policy": "balanced", "ctx": ctx,
            "auto_tier": False, "features": ["mobile"] if (dev.client_only or dev.termux) else ["inference"],
            "note": note}


if __name__ == "__main__":
    import json
    d = detect()
    print(json.dumps({"device": d.to_dict(), "recommendation": recommend(d)}, indent=2))