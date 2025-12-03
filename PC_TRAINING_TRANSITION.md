# PC Training Transition - Quick Start

**Date**: December 4, 2025  
**From**: Jetson Orin Nano (training not feasible)  
**To**: PC with RTX 2060 (recommended for training)

---

## What Was Done on Jetson

✅ **Successfully Completed**:
- Frame extraction from SVO2 files
- Annotation of 612 training images + 168 validation images
- 73-bucket YOLO training structure created
- Complete annotation workflow tested

❌ **Failed - Training on Jetson**:
- Out of Memory kills during first epoch
- Memory: 8GB unified insufficient for YOLO training
- cuDNN 8/9 version incompatibility issues
- Conclusion: Use Jetson for extraction/annotation/inference only

---

## What's Ready for PC

### 1. Codebase Clean
- ✅ All Jetson-specific workarounds removed from `training_app.py`
- ✅ Standard CUDA code (no cuDNN hacks)
- ✅ Cross-platform requirements.txt
- ✅ All changes committed and pushed to GitHub

### 2. Documentation Complete
- ✅ `docs/pc-setup-guide.md` – Complete PC setup instructions (650+ lines)
- ✅ `docs/fieldtest-learnings.md` – Jetson analysis and workflow (200+ lines)
- ✅ `docs/jetson-setup-guide.md` – Updated with training limitations
- ✅ `README.md` – Workflow recommendations updated

### 3. Dataset Ready
- ✅ Training: 612 images annotated
- ✅ Validation: 168 images annotated
- ✅ 73-bucket structure complete
- ✅ Located: `/media/angelo/DRONE_DATA1/YoloTraining-1.Iteration/`

---

## PC Setup Steps (Execute on PC)

### 1. Clone Repository
```bash
git clone https://github.com/xX2Angelo8Xx/SVO2-Handler.git
cd SVO2-Handler
```

### 2. Create Virtual Environment
```bash
# Linux
python3.10 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
.\venv\Scripts\activate
```

### 3. Install PyTorch with CUDA
```bash
# CUDA 12.1 (recommended for RTX 2060)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Or CUDA 11.8 (alternative)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### 4. Install Project Dependencies
```bash
pip install -r requirements.txt
```

### 5. Verify CUDA
```bash
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"
```

Expected output:
```
CUDA available: True
GPU: NVIDIA GeForce RTX 2060
```

### 6. Transfer Dataset (from Jetson)
```bash
# Option A: rsync over network
rsync -avz angelo@jetson:/media/angelo/DRONE_DATA1/YoloTraining-1.Iteration/ \
         ./YoloTraining-1.Iteration/

# Option B: USB drive
# Copy from Jetson to USB, then from USB to PC
```

### 7. Launch Training App
```bash
python -m svo_handler.training_app
```

---

## Recommended Training Configuration

**For RTX 2060 (6GB VRAM)**:

### Conservative (guaranteed to work):
- Model: YOLOv8n
- Image Size: 640x640
- Batch Size: 16
- Epochs: 100
- Expected Time: 1.5-2 hours
- Expected Speed: ~30-40 FPS

### Aggressive (max quality):
- Model: YOLOv8n
- Image Size: Source (HD720 = 1280x720)
- Batch Size: 8
- Epochs: 100
- Expected Time: 3-4 hours
- Expected Speed: ~15-20 FPS

---

## Verification Checklist

Before starting training, verify:

- [ ] Python 3.10 or 3.11 installed
- [ ] `nvidia-smi` shows RTX 2060
- [ ] `torch.cuda.is_available()` returns `True`
- [ ] Dataset copied to PC (653 training + 186 validation images)
- [ ] Training app launches without errors
- [ ] Can select dataset folder in GUI

---

## What to Expect

### Training Progress
- **First epoch**: Slowest (dataset initialization, ~5-10 min)
- **Subsequent epochs**: Faster (cached data, ~30-60 sec each)
- **GPU usage**: Should be 90-100% during training
- **VRAM usage**: ~4-5GB out of 6GB

### Checkpoints
- **Saved every epoch**: `yolo_training/run_xxxx/weights/last.pt`
- **Best model**: `yolo_training/run_xxxx/weights/best.pt`
- **Metrics**: `yolo_training/run_xxxx/results.csv`

### After Training
- Transfer `best.pt` back to Jetson
- Convert to TensorRT on Jetson for inference
- Deploy to drone flight controller

---

## Troubleshooting

### CUDA Not Available
```bash
# Check driver
nvidia-smi

# Reinstall PyTorch with CUDA
pip uninstall torch torchvision
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

### Out of Memory
- Reduce batch size: 16 → 8 → 4
- Reduce image size: 640 → 512 → 416
- Close other GPU applications

### Slow Training
- Check GPU usage: `nvidia-smi -l 1`
- Should be 90-100% GPU utilization
- If low: increase workers (4-8)

---

## Documentation References

1. **[PC Setup Guide](docs/pc-setup-guide.md)** – Detailed installation guide
2. **[Training Guide](docs/training-guide.md)** – Feature documentation
3. **[Fieldtest Learnings](docs/fieldtest-learnings.md)** – Jetson analysis

---

## Current Status

✅ **Jetson**:
- All findings documented
- Code cleaned up
- Changes pushed to GitHub
- Ready for extraction/annotation/inference workflows

✅ **PC**:
- Setup documentation complete
- Clean codebase ready
- Standard PyTorch installation
- Ready for training

🔄 **Next Action**: Execute PC setup steps above

---

**Last Updated**: December 4, 2025  
**Repository**: https://github.com/xX2Angelo8Xx/SVO2-Handler  
**Branch**: main  
**Latest Commit**: 5477697 - "Document Jetson training limitations and prepare for PC training"
