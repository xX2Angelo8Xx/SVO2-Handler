# PC Setup Guide for YOLO Training

**Target Hardware**: Desktop/Laptop with NVIDIA GPU (RTX 2060 or better)  
**Operating System**: Windows 10/11 or Linux  
**Last Updated**: December 4, 2025

---

## Table of Contents

1. [Overview](#overview)
2. [System Requirements](#system-requirements)
3. [Quick Setup](#quick-setup)
4. [Detailed Installation](#detailed-installation)
5. [Verification](#verification)
6. [Troubleshooting](#troubleshooting)
7. [Performance Expectations](#performance-expectations)

---

## Overview

This guide provides step-by-step instructions for setting up the SVO2 Handler training environment on a PC with NVIDIA GPU. Unlike Jetson setup, PC setup is straightforward with standard PyTorch installation.

**Why train on PC instead of Jetson?**
- ✅ Sufficient dedicated VRAM (6GB+ vs 8GB shared)
- ✅ Standard CUDA/PyTorch installation (no special wheels)
- ✅ No cuDNN version conflicts
- ✅ 2-3x faster training (more CUDA cores, better memory bandwidth)
- ✅ Larger batch sizes possible (16-32 vs <8)

See [fieldtest-learnings.md](./fieldtest-learnings.md#yolo-training-attempts-on-jetson-orin-nano) for Jetson limitations.

---

## System Requirements

### Minimum Hardware
- **GPU**: NVIDIA GTX 1060 (6GB VRAM) or better
- **CPU**: 4+ cores
- **RAM**: 16GB system RAM
- **Storage**: 50GB+ free space (for datasets and models)

### Recommended Hardware
- **GPU**: NVIDIA RTX 2060 or better (6GB+ VRAM)
- **CPU**: 6+ cores
- **RAM**: 32GB system RAM
- **Storage**: 100GB+ SSD

### Software Prerequisites

#### Linux
- **OS**: Ubuntu 20.04+ or equivalent
- **Python**: 3.10 or 3.11
- **CUDA**: 11.8 or 12.1 (installed with PyTorch)
- **Display**: X11 for GUI applications

#### Windows
- **OS**: Windows 10/11 (64-bit)
- **Python**: 3.10 or 3.11
- **CUDA**: 11.8 or 12.1 (installed with PyTorch)
- **Visual C++ Redistributable**: Latest version

---

## Quick Setup

### 1. Check GPU Availability

**Windows**:
```powershell
nvidia-smi
```

**Linux**:
```bash
nvidia-smi
```

You should see your GPU listed with CUDA version.

### 2. Clone Repository

```bash
git clone https://github.com/xX2Angelo8Xx/SVO2-Handler.git
cd SVO2-Handler
```

### 3. Create Virtual Environment

**Linux/macOS**:
```bash
python3.10 -m venv venv
source venv/bin/activate
```

**Windows**:
```powershell
python -m venv venv
.\venv\Scripts\activate
```

### 4. Install Dependencies

**Option A - With CUDA 12.1** (Recommended for RTX 30/40 series):
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

**Option B - With CUDA 11.8** (For older GPUs):
```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
pip install -r requirements.txt
```

**Note**: Unlike Jetson, you do NOT need special wheels. Standard PyPI packages work perfectly.

### 5. Verify Installation

```bash
python -c "import torch; print(f'PyTorch: {torch.__version__}'); print(f'CUDA available: {torch.cuda.is_available()}'); print(f'Device: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"
```

Expected output:
```
PyTorch: 2.5.1+cu121
CUDA available: True
Device: NVIDIA GeForce RTX 2060
```

### 6. Run Training App

```bash
python -m svo_handler.training_app
```

---

## Detailed Installation

### Step 1: Install Python

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install python3.10 python3.10-venv python3.10-dev
```

#### Windows
Download Python 3.10 from [python.org](https://www.python.org/downloads/) and install with:
- ✅ Add Python to PATH
- ✅ Install pip
- ✅ Install for all users (optional)

### Step 2: Install NVIDIA Drivers

#### Linux
```bash
# Check recommended driver
ubuntu-drivers devices

# Install recommended driver
sudo ubuntu-drivers autoinstall

# Or install specific version
sudo apt install nvidia-driver-535

# Reboot
sudo reboot
```

#### Windows
Download latest driver from [NVIDIA website](https://www.nvidia.com/Download/index.aspx) and install.

### Step 3: Verify CUDA

```bash
nvidia-smi
```

Look for CUDA version in the top-right corner (e.g., "CUDA Version: 12.2").

**Important**: This is the **maximum** CUDA version supported. PyTorch can use older CUDA versions (e.g., CUDA 11.8 works on driver supporting 12.2).

### Step 4: Install PyTorch

Choose CUDA version based on your needs:

**CUDA 12.1** (Recommended):
- Latest features
- Better performance on RTX 30/40 series
- Compatible with drivers 525+

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

**CUDA 11.8** (Stable):
- Wider compatibility
- Better tested
- Works with older drivers

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

**CPU-only** (Not recommended for training):
```bash
pip install torch torchvision
```

### Step 5: Install Project Dependencies

```bash
# Clone repository
git clone https://github.com/xX2Angelo8Xx/SVO2-Handler.git
cd SVO2-Handler

# Create virtual environment
python3.10 -m venv venv
source venv/bin/activate  # Linux/macOS
# or
.\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Step 6: Download Pre-trained Models

```bash
# YOLOv8n (nano) - fastest, least accurate
wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt

# YOLOv11n (nano) - newer architecture
wget https://github.com/ultralytics/assets/releases/download/v8.2.0/yolo11n.pt
```

Or models will auto-download on first training run.

---

## Verification

### Complete Verification Script

Save as `verify_setup.py`:

```python
#!/usr/bin/env python3
"""Verify SVO2 Handler training environment setup."""

import sys
from pathlib import Path

def check_python():
    """Check Python version."""
    version = sys.version_info
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    if version.major != 3 or version.minor < 10:
        print("  ⚠️  Python 3.10+ recommended")
    return True

def check_torch():
    """Check PyTorch and CUDA."""
    try:
        import torch
        print(f"✓ PyTorch {torch.__version__}")
        
        if torch.cuda.is_available():
            print(f"✓ CUDA available: {torch.version.cuda}")
            print(f"✓ cuDNN version: {torch.backends.cudnn.version()}")
            print(f"✓ GPU: {torch.cuda.get_device_name(0)}")
            print(f"✓ GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            
            # Quick performance test
            x = torch.randn(1000, 1000, device='cuda')
            y = torch.randn(1000, 1000, device='cuda')
            torch.cuda.synchronize()
            
            import time
            start = time.time()
            for _ in range(100):
                z = torch.mm(x, y)
            torch.cuda.synchronize()
            elapsed = time.time() - start
            
            print(f"✓ GPU performance: {100/elapsed:.1f} matmul ops/sec")
            return True
        else:
            print("✗ CUDA not available")
            print("  Check: nvidia-smi shows GPU?")
            print("  Check: PyTorch installed with CUDA support?")
            return False
            
    except ImportError:
        print("✗ PyTorch not installed")
        print("  Install: pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
        return False

def check_ultralytics():
    """Check Ultralytics YOLO."""
    try:
        import ultralytics
        print(f"✓ Ultralytics {ultralytics.__version__}")
        return True
    except ImportError:
        print("✗ Ultralytics not installed")
        print("  Install: pip install ultralytics")
        return False

def check_pyside6():
    """Check PySide6 for GUI."""
    try:
        from PySide6 import QtWidgets
        print(f"✓ PySide6 installed")
        return True
    except ImportError:
        print("✗ PySide6 not installed")
        print("  Install: pip install PySide6")
        return False

def check_opencv():
    """Check OpenCV."""
    try:
        import cv2
        print(f"✓ OpenCV {cv2.__version__}")
        return True
    except ImportError:
        print("✗ OpenCV not installed")
        print("  Install: pip install opencv-python")
        return False

def main():
    """Run all checks."""
    print("=" * 60)
    print("SVO2 Handler Training Environment Verification")
    print("=" * 60)
    print()
    
    checks = [
        ("Python", check_python),
        ("PyTorch + CUDA", check_torch),
        ("Ultralytics", check_ultralytics),
        ("PySide6", check_pyside6),
        ("OpenCV", check_opencv),
    ]
    
    results = []
    for name, check_fn in checks:
        print(f"\n{name}:")
        print("-" * 60)
        results.append(check_fn())
    
    print("\n" + "=" * 60)
    if all(results):
        print("✓ All checks passed! Ready to train.")
    else:
        print("✗ Some checks failed. See messages above.")
    print("=" * 60)
    
    return 0 if all(results) else 1

if __name__ == "__main__":
    sys.exit(main())
```

Run verification:
```bash
python verify_setup.py
```

---

## Troubleshooting

### Issue 1: CUDA Not Available

**Symptom**:
```python
>>> torch.cuda.is_available()
False
```

**Solution**:

1. Check NVIDIA driver:
```bash
nvidia-smi
```
If this fails, reinstall NVIDIA driver.

2. Check PyTorch CUDA version:
```bash
pip show torch
```
Look for `+cu121` or `+cu118` in version. If just `torch==2.x.x`, you have CPU-only version.

3. Reinstall with CUDA:
```bash
pip uninstall torch torchvision
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### Issue 2: Out of Memory During Training

**Symptom**:
```
RuntimeError: CUDA out of memory
```

**Solutions**:

1. **Reduce batch size** in training GUI:
   - Try: 16 → 8 → 4
   - RTX 2060 (6GB): batch size 8-16 works well

2. **Use smaller image size**:
   - Try: 640 → 512 → 416
   - Or use "Source" resolution (HD720 = 1280x720)

3. **Close other GPU applications**:
```bash
# Check GPU usage
nvidia-smi
```

4. **Disable dataset caching** (slower but less memory):
   - In training config, set `cache=False`

### Issue 3: Slow Training Speed

**Symptom**:
- Training much slower than expected
- GPU utilization low (<50%)

**Solutions**:

1. **Check GPU is being used**:
```python
import torch
print(torch.cuda.is_available())  # Must be True
print(torch.cuda.current_device())  # Should be 0
```

2. **Increase number of workers**:
   - In training GUI, set workers to 4-8
   - Rule of thumb: workers = CPU cores / 2

3. **Enable AMP (Automatic Mixed Precision)**:
   - Should be enabled by default
   - Faster training, lower memory usage

4. **Check CPU bottleneck**:
```bash
# Linux
htop

# Windows
Task Manager → Performance
```

### Issue 4: PySide6 Import Error

**Symptom**:
```
ImportError: cannot import name 'QtWidgets' from 'PySide6'
```

**Solution**:
```bash
pip install --upgrade PySide6
```

### Issue 5: ZED SDK Not Found (Optional)

**Note**: ZED SDK is only needed for SVO2 extraction, NOT for training.

If you need SVO2 extraction on PC:
1. Download ZED SDK from [stereolabs.com](https://www.stereolabs.com/developers/release)
2. Install for your OS
3. Verify: `python -c "import pyzed.sl as sl; print('ZED OK')"`

For training only, ZED SDK is not required.

---

## Performance Expectations

### Training Speed Comparison

**Dataset**: 612 training images, 168 validation images  
**Model**: YOLOv8n (3M parameters)  
**Image Size**: 640x640  
**Batch Size**: 16

| GPU | VRAM | Training Speed | 100 Epochs Time |
|-----|------|----------------|-----------------|
| Jetson Orin Nano | 8GB shared | N/A (OOM) | N/A |
| RTX 2060 | 6GB | ~30-40 FPS | 1.5-2 hours |
| RTX 3060 | 12GB | ~50-60 FPS | 1-1.5 hours |
| RTX 3070 | 8GB | ~60-70 FPS | ~1 hour |
| RTX 4070 | 12GB | ~80-100 FPS | ~40 mins |

**HD720 Source Resolution** (1280x720, batch size 8):

| GPU | VRAM | Training Speed | 100 Epochs Time |
|-----|------|----------------|-----------------|
| RTX 2060 | 6GB | ~15-20 FPS | 3-4 hours |
| RTX 3060 | 12GB | ~25-35 FPS | 2-3 hours |
| RTX 4070 | 12GB | ~40-50 FPS | 1.5-2 hours |

### Memory Usage

**Typical memory footprint**:
- Model (YOLOv8n): ~500MB
- Batch (16 images @ 640x640): ~1-2GB
- Training buffers: ~1-2GB
- **Total**: ~3-4GB VRAM

**With HD720 source resolution**:
- Batch (8 images @ 1280x720): ~2-3GB
- **Total**: ~4-5GB VRAM

**Recommendations**:
- 6GB VRAM: Batch 8-16 @ 640x640, or batch 4-8 @ HD720
- 8GB+ VRAM: Batch 16-32 @ 640x640, or batch 8-16 @ HD720
- 12GB+ VRAM: No memory concerns for typical training

### Batch Size Guidelines

| VRAM | 640x640 Max Batch | HD720 Max Batch |
|------|-------------------|-----------------|
| 4GB | 4-8 | 2-4 |
| 6GB | 8-16 | 4-8 |
| 8GB | 16-32 | 8-16 |
| 12GB+ | 32+ | 16-32 |

---

## Next Steps

1. **Transfer dataset from Jetson** (if applicable):
```bash
# On PC, from Jetson
rsync -avz jetson:/media/angelo/DRONE_DATA1/YoloTraining-1.Iteration/ \
         ./YoloTraining-1.Iteration/
```

2. **Launch training app**:
```bash
python -m svo_handler.training_app
```

3. **Configure training**:
   - Select dataset folder
   - Choose model (YOLOv8n recommended)
   - Set image size (640 or Source for HD720)
   - Set batch size (16 for RTX 2060)
   - Set epochs (100 recommended)

4. **Start training** and monitor:
   - Training progress in GUI
   - GPU usage: `nvidia-smi -l 1`
   - Results in `yolo_training/run_xxxx/`

5. **After training**:
   - Best model: `yolo_training/run_xxxx/weights/best.pt`
   - Validation metrics: `yolo_training/run_xxxx/results.csv`
   - Transfer to Jetson for deployment

---

## Additional Resources

### Documentation
- [Training Guide](./training-guide.md) - Training strategy and best practices
- [Applications Guide](./applications.md) - All four applications
- [Jetson Setup Guide](./jetson-setup-guide.md) - Jetson limitations and setup

### External Links
- [PyTorch Installation](https://pytorch.org/get-started/locally/)
- [Ultralytics Documentation](https://docs.ultralytics.com/)
- [CUDA Toolkit](https://developer.nvidia.com/cuda-downloads)
- [NVIDIA Drivers](https://www.nvidia.com/Download/index.aspx)

### Support
- GitHub Issues: https://github.com/xX2Angelo8Xx/SVO2-Handler/issues
- PyTorch Forums: https://discuss.pytorch.org/
- Ultralytics Discord: https://discord.com/invite/ultralytics

---

**Last Updated**: December 4, 2025  
**Author**: Angelo (xX2Angelo8Xx)
