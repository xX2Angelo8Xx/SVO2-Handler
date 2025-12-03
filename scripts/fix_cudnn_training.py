#!/usr/bin/env python3
"""
Workaround script for cuDNN compatibility issues on Jetson.

This script disables cuDNN benchmarking and deterministic mode to work around
cuDNN 8/9 compatibility issues when training YOLO models.

Usage:
    Set this before importing ultralytics or running training:
    
    export PYTORCH_CUDNN_BENCHMARK=0
    export PYTORCH_DETERMINISTIC=0
    
Or run training with:
    python scripts/fix_cudnn_training.py
"""

import os
import sys

# Disable cuDNN benchmarking (can cause compatibility issues)
os.environ['PYTORCH_CUDNN_BENCHMARK'] = '0'
os.environ['PYTORCH_DETERMINISTIC'] = '0'

# Set cuDNN to use fallback algorithms
os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'

import torch

# Disable cuDNN benchmarking in PyTorch
torch.backends.cudnn.benchmark = False
torch.backends.cudnn.deterministic = False

# Allow TF32 for better performance on Ampere
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True

print("✅ cuDNN compatibility settings applied")
print(f"   - cudnn.benchmark: {torch.backends.cudnn.benchmark}")
print(f"   - cudnn.deterministic: {torch.backends.cudnn.deterministic}")
print(f"   - CUDA TF32: {torch.backends.cuda.matmul.allow_tf32}")

if __name__ == "__main__":
    print("\n🚀 Launching training app with cuDNN workarounds...")
    
    # Import and run training app
    from svo_handler import training_app
    training_app.main()
