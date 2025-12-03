# Learnings from Drone Field Test (Producer of SVO2 Files)

Context: Source `.svo2` files come from a Jetson Orin Nano + ZED 2i stack (see `/home/angelo/Projects/Drone-Fieldtest`). These notes capture the most relevant operational constraints and patterns to inform the SVO2 Handler design.

## Capture & Encoding
- Recordings use ZED SDK 4.x in LOSSLESS mode only (NVENC/H.264/H.265 not available on Orin Nano). Expect large files (HD720@60 ≈ ~26 MB/s; ~10 GB per 4 minutes).
- Source FPS commonly 30 or 60; always read metadata from the SVO header and surface it in the UI before configuring extraction/downsampling.
- CORRUPTED_FRAME warnings were treated as non-fatal during capture; downstream extraction should log and continue if individual frames fail to decode.

## Filesystem & Storage
- FAT32 has a hard 4GB limit; corruption occurs beyond ~4.29GB. Field stack enforced a 3.75GB safety cap. Prefer NTFS/exFAT for both recording and large exports.
- When writing many frames/depth dumps, validate available space and warn if output targets FAT32 or low-free-space volumes.

## Extraction Patterns
- Downsampling used simple frame skipping (`grab` loop, modulo on frame index). UI slider should map target FPS to skip interval against source FPS (e.g., 60→10 FPS = keep every 6th frame).
- Left camera was the default training source; keep explicit left/right choice in the UI and in output path naming.
- Prior tool wrote organized folders derived from flight/session name; mimic clear, deterministic output structure (session/stream/frame_xxxxxx.jpg) and include a manifest.

## Depth Data
- Raw depth exports were stored as float32 arrays preceded by a small header (int width, int height, int frame_number), one file per frame. Visualization used jet colormap with invalid depth (NaN/Inf/<=0) set to black.
- Depth mode selection is important: match the capture depth model when possible, and surface the chosen model in manifests for training provenance.

## Concurrency & Robustness
- Monitor/worker loops must break on STOPPING to avoid deadlocks (avoid `continue` inside stop branches); join worker threads from the controller, not from within the workers.
- Keep UI-responsive by offloading decode/write work to workers with bounded queues; provide cancellation that drains gracefully.

For the full upstream rationale, see `docs/CRITICAL_LEARNINGS_v1.3.md` in the Drone-Fieldtest repository.

---

## YOLO Training Attempts on Jetson Orin Nano

**Date**: December 2025  
**Hardware**: Jetson Orin Nano Super, 8GB RAM, JetPack 6.0, 1024 CUDA cores  
**Objective**: Train YOLOv8n for target detection at HD720 source resolution  
**Outcome**: Not feasible - recommend PC training instead

### Issues Encountered

#### 1. PyTorch CUDA Installation Complexity
- **Problem**: Standard PyPI `pip install torch` installs CPU-only version (150x slower)
- **Solution**: Must use NVIDIA pre-built wheels from nvidia.box.com
  - torch-2.3.0 with CUDA 12.2 support (202MB wheel)
  - torchvision-0.18.0 (1.4MB wheel)
  - Requires manual download, can't use standard `pip install torch`
- **Complexity**: High barrier for reproducible setups

#### 2. cuDNN Version Incompatibility
- **Problem**: PyTorch 2.3 compiled with cuDNN 8, JetPack 6.0 ships with cuDNN 9
- **Symptoms**: 
  ```
  CUDNN_STATUS_EXECUTION_FAILED
  GET was unable to find an engine to execute this computation
  Plan failed with a cudnnException
  ```
- **Attempted Solutions**:
  1. Install cuDNN 8.9.7 alongside cuDNN 9 (coexistence)
  2. Create symlinks: `libcudnn.so.8 → libcudnn.so.9`
  3. Disable cuDNN benchmarking: `torch.backends.cudnn.benchmark = False`
  4. **Final solution**: Complete cuDNN disabling: `torch.backends.cudnn.enabled = False`
- **Result**: Training starts but uses PyTorch fallback CUDA kernels (~10-20% slower)

#### 3. Out of Memory (OOM) Kills
- **Problem**: Training process killed during first epoch initialization
- **Configuration**:
  - Dataset: 612 training images, 168 validation images
  - Batch size: 16
  - Image size: 640x640 (default)
  - Model: YOLOv8n (3M parameters)
- **Memory Usage**:
  - Base OS + JetPack: ~2GB
  - ZED SDK cached: ~1GB
  - PyTorch + model: ~1.5GB
  - Dataset caching: ~1-2GB
  - Training buffers: ~2-3GB
  - **Total**: >8GB available RAM
- **Mitigations Attempted**:
  - Reduce batch size to 8 or 4 → Still OOM
  - Disable dataset caching (`cache=False`) → Still OOM
  - Workers reduced to 2 → Still OOM
- **Conclusion**: 8GB unified memory insufficient for YOLO training with full dataset

#### 4. Performance Limitations
- **Expected Speed** (if training succeeded):
  - With cuDNN: ~15-20 FPS at HD720 source resolution
  - Without cuDNN: ~10-15 FPS
  - Training time: 3-4 hours for 100 epochs
- **GPU Utilization**: Only 1024 CUDA cores (vs 1920 on RTX 2060)
- **Memory Bandwidth**: Shared unified memory (slower than dedicated VRAM)

### Lessons Learned

#### ✅ What Worked
1. **Frame extraction**: Jetson handles SVO2 decoding well (~30-60 FPS)
2. **Annotation tools**: Viewer and checker apps run smoothly
3. **CUDA availability**: torch.cuda.is_available() = True after proper installation
4. **Model loading**: Pre-trained weights load successfully
5. **Dataset scanning**: Successfully scanned and cached 612 training images

#### ❌ What Didn't Work
1. **Training execution**: OOM kills during first epoch
2. **cuDNN compatibility**: Version mismatch requires complete disabling
3. **Memory constraints**: 8GB insufficient for full YOLO training workflow
4. **Installation complexity**: Non-standard PyTorch installation, high maintenance

### Recommended Workflow

**✅ Use Jetson Orin Nano For:**
- SVO2 file extraction (capture device is Jetson anyway)
- Frame export and preprocessing
- Annotation (Viewer/Annotator app)
- Verification (Annotation Checker app)
- **Inference deployment** (post-training, with TensorRT optimization)
- Real-time drone operations (once model is trained)

**❌ Do NOT Use Jetson For:**
- YOLO model training (insufficient memory)
- Large batch training workflows
- Iterative model experimentation

**✅ Use PC (RTX 2060 or better) For:**
- **YOLO training** (6GB VRAM, standard CUDA/cuDNN)
- Model experimentation and hyperparameter tuning
- Batch size optimization
- Multi-epoch training runs
- TensorRT conversion and optimization

### Training Workflow Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    JETSON ORIN NANO                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ SVO2 Capture │→ │ Frame Export │→ │  Annotation  │      │
│  │  (ZED 2i)    │  │   (HD720)    │  │ (Viewer App) │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓ (Copy annotated dataset)
┌─────────────────────────────────────────────────────────────┐
│                    PC (RTX 2060+)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ YOLO Training│→ │   Validation │→ │    Export    │      │
│  │  (100 epochs)│  │  (mAP, etc.) │  │ (.pt/.onnx)  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓ (Deploy trained model)
┌─────────────────────────────────────────────────────────────┐
│                    JETSON ORIN NANO                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  TensorRT    │→ │   Inference  │→ │ Flight Ctrl  │      │
│  │ Optimization │  │  (Real-time) │  │ Integration  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### Performance Comparison: Jetson vs PC Training

| Metric | Jetson Orin Nano | PC (RTX 2060) | Factor |
|--------|------------------|---------------|--------|
| CUDA Cores | 1024 | 1920 | 1.9x |
| Memory | 8GB unified | 6GB VRAM + system RAM | Dedicated better |
| Memory Bandwidth | ~68 GB/s | ~336 GB/s | 5x |
| PyTorch Install | Custom wheels | Standard pip | Easy |
| cuDNN Compatibility | Version conflicts | Native support | No issues |
| Training Speed | N/A (OOM) | ~30-50 FPS expected | - |
| Batch Size | <8 (OOM) | 16-32 | 3-4x |
| 100 Epochs | N/A (OOM) | ~1-2 hours | - |

### Technical Details Preserved

**Jetson-Specific Code** (for reference, removed from main training app):
```python
# Disable cuDNN completely for Jetson compatibility
import torch
torch.backends.cudnn.enabled = False  # Use PyTorch CUDA fallback
torch.backends.cuda.matmul.allow_tf32 = True  # Keep TF32 for Ampere
```

**Why This Was Needed**:
- cuDNN 8.9.7 (PyTorch 2.3) vs cuDNN 9.3.0 (JetPack 6.0) incompatibility
- Symlinks work for library loading but fail at runtime execution
- Disabling cuDNN uses PyTorch's native CUDA kernels (slower but compatible)

**Why It's Not Needed on PC**:
- Standard CUDA toolkit installation includes matching cuDNN version
- PyTorch from pip/conda includes compatible CUDA/cuDNN binaries
- No version conflicts in standard development environments

### Documentation Created

1. **docs/jetson-setup-guide.md** (585 lines):
   - Complete PyTorch CUDA installation guide
   - cuDNN 8 installation alongside cuDNN 9
   - 6 troubleshooting issues with solutions
   - Performance benchmarks
   - **Conclusion**: Now includes training feasibility warning

2. **scripts/fix_cudnn_training.py**:
   - Helper script for cuDNN workarounds
   - **Status**: No longer needed for PC training

### Final Recommendation

**Do NOT attempt YOLO training on Jetson Orin Nano 8GB**. Use it for:
- Data capture and extraction
- Annotation workflows
- Inference deployment (with TensorRT)

**Use PC with dedicated GPU (RTX 2060+) for training**:
- Standard CUDA/PyTorch installation
- Sufficient VRAM for batch training
- Faster iteration cycles
- Better development experience

**Data Transfer Strategy**:
```bash
# On Jetson: Export annotated dataset
rsync -avz /media/angelo/DRONE_DATA1/YoloTraining-1.Iteration/ \
         pc:/path/to/training/

# On PC: Train model
python -m svo_handler.training_app

# Transfer trained model back to Jetson
scp runs/best.pt jetson:/path/to/deployment/
```
