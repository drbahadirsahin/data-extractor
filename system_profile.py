from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GPUInfo:
    vendor: str
    name: str
    memory_gb: float | None = None
    driver: str | None = None


@dataclass
class SystemProfile:
    os_name: str
    os_version: str
    machine: str
    python_version: str
    cpu_count: int
    total_memory_gb: float | None
    available_memory_gb: float | None
    gpus: list[GPUInfo] = field(default_factory=list)


@dataclass
class InferenceRecommendation:
    mode: str
    confidence: str
    reasons: list[str]


def collect_system_profile() -> SystemProfile:
    total_memory_bytes, available_memory_bytes = get_memory_info()
    return SystemProfile(
        os_name=platform.system(),
        os_version=platform.version(),
        machine=platform.machine(),
        python_version=platform.python_version(),
        cpu_count=os.cpu_count() or 1,
        total_memory_gb=bytes_to_gb(total_memory_bytes),
        available_memory_gb=bytes_to_gb(available_memory_bytes),
        gpus=detect_gpus(),
    )


def recommend_inference_mode(profile: SystemProfile) -> InferenceRecommendation:
    gpu_vram_values = [gpu.memory_gb for gpu in profile.gpus if gpu.memory_gb is not None]
    max_gpu_vram = max(gpu_vram_values) if gpu_vram_values else None
    reasons: list[str] = []

    if max_gpu_vram is not None and max_gpu_vram >= 10:
        reasons.append(f"Detected GPU VRAM is {max_gpu_vram:.1f} GB.")
        reasons.append("Local Ollama is likely viable on this device.")
        return InferenceRecommendation(mode="local_ollama", confidence="high", reasons=reasons)

    if max_gpu_vram is not None and max_gpu_vram >= 6:
        reasons.append(f"Detected GPU VRAM is {max_gpu_vram:.1f} GB.")
        reasons.append("Local inference may work, but remote inference is safer for stability.")
        return InferenceRecommendation(mode="remote_ollama", confidence="medium", reasons=reasons)

    if profile.total_memory_gb is not None and profile.total_memory_gb >= 16:
        reasons.append(f"System memory is {profile.total_memory_gb:.1f} GB.")
        reasons.append("No strong GPU was detected, so remote Ollama is the safer default.")
        return InferenceRecommendation(mode="remote_ollama", confidence="medium", reasons=reasons)

    memory_label = f"{profile.total_memory_gb:.1f} GB" if profile.total_memory_gb is not None else "unknown"
    reasons.append(f"System memory is {memory_label}.")
    reasons.append("No suitable CUDA-class GPU was detected.")
    reasons.append("API-backed inference is recommended for first-run defaults.")
    return InferenceRecommendation(mode="openai_compatible", confidence="high", reasons=reasons)


def get_memory_info() -> tuple[int | None, int | None]:
    if sys.platform == "darwin":
        total = read_macos_memsize()
        return total, None
    if sys.platform.startswith("linux"):
        return read_linux_meminfo()
    if os.name == "nt":
        return read_windows_meminfo()
    return None, None


def read_macos_memsize() -> int | None:
    output = run_command(["sysctl", "-n", "hw.memsize"])
    if not output:
        return None
    try:
        return int(output.strip())
    except ValueError:
        return None


def read_linux_meminfo() -> tuple[int | None, int | None]:
    meminfo_path = Path("/proc/meminfo")
    if not meminfo_path.exists():
        return None, None

    total_kb: int | None = None
    available_kb: int | None = None
    for line in meminfo_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("MemTotal:"):
            total_kb = parse_meminfo_kb(line)
        elif line.startswith("MemAvailable:"):
            available_kb = parse_meminfo_kb(line)
    return kb_to_bytes(total_kb), kb_to_bytes(available_kb)


def read_windows_meminfo() -> tuple[int | None, int | None]:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    memory_status = MEMORYSTATUSEX()
    memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status)):
        return None, None
    return int(memory_status.ullTotalPhys), int(memory_status.ullAvailPhys)


def detect_gpus() -> list[GPUInfo]:
    nvidia_gpus = detect_nvidia_gpus()
    if nvidia_gpus:
        return nvidia_gpus
    return []


def detect_nvidia_gpus() -> list[GPUInfo]:
    output = run_command(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if not output:
        return []

    gpus: list[GPUInfo] = []
    for line in output.splitlines():
        parts = [item.strip() for item in line.split(",")]
        if len(parts) < 2:
            continue
        memory_gb = None
        try:
            memory_gb = round(float(parts[1]) / 1024, 2)
        except ValueError:
            memory_gb = None
        gpus.append(
            GPUInfo(
                vendor="NVIDIA",
                name=parts[0],
                memory_gb=memory_gb,
                driver=parts[2] if len(parts) > 2 else None,
            )
        )
    return gpus


def run_command(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip()


def parse_meminfo_kb(line: str) -> int | None:
    parts = line.split()
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


def kb_to_bytes(value: int | None) -> int | None:
    if value is None:
        return None
    return value * 1024


def bytes_to_gb(value: int | None) -> float | None:
    if value is None:
        return None
    return round(value / (1024 ** 3), 2)
