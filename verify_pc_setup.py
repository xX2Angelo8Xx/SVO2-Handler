#!/usr/bin/env python3
"""
Verify SVO2 Handler training environment setup on PC.

This script checks:
- Python version
- PyTorch with CUDA support
- GPU availability and performance
- All required dependencies
- Training app can import

Run this FIRST on your PC after setup to ensure everything is ready.
"""

import sys
from pathlib import Path


def print_header(text: str) -> None:
    """Print section header."""
    print(f"\n{'=' * 70}")
    print(f"  {text}")
    print('=' * 70)


def print_subheader(text: str) -> None:
    """Print subsection header."""
    print(f"\n{text}")
    print('-' * 70)


def check_python() -> bool:
    """Check Python version."""
    print_subheader("Python Version")
    version = sys.version_info
    print(f"✓ Python {version.major}.{version.minor}.{version.micro}")
    
    if version.major != 3:
        print("  ✗ Python 3 required")
        return False
    if version.minor < 10:
        print("  ⚠️  Python 3.10+ recommended (you have 3.{version.minor})")
        return False
    
    return True


def check_torch() -> bool:
    """Check PyTorch and CUDA."""
    print_subheader("PyTorch + CUDA")
    
    try:
        import torch
        print(f"✓ PyTorch version: {torch.__version__}")
        
        # Check for CUDA compilation
        if '+cu' not in torch.__version__:
            print("  ✗ PyTorch installed WITHOUT CUDA support")
            print("  Install with: pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
            return False
        
        # Check CUDA availability
        if not torch.cuda.is_available():
            print("  ✗ CUDA not available")
            print("  Check: nvidia-smi shows GPU?")
            print("  Check: NVIDIA drivers installed?")
            return False
        
        print(f"✓ CUDA available: {torch.version.cuda}")
        print(f"✓ cuDNN version: {torch.backends.cudnn.version()}")
        print(f"✓ GPU count: {torch.cuda.device_count()}")
        print(f"✓ GPU name: {torch.cuda.get_device_name(0)}")
        
        props = torch.cuda.get_device_properties(0)
        print(f"✓ GPU memory: {props.total_memory / 1024**3:.1f} GB")
        print(f"✓ CUDA cores: {props.multi_processor_count * 64}")
        
        # Performance test
        print("\n  Running GPU performance test...")
        x = torch.randn(1000, 1000, device='cuda')
        y = torch.randn(1000, 1000, device='cuda')
        torch.cuda.synchronize()
        
        import time
        start = time.time()
        for _ in range(100):
            z = torch.mm(x, y)
        torch.cuda.synchronize()
        elapsed = time.time() - start
        
        ops_per_sec = 100 / elapsed
        print(f"✓ GPU performance: {ops_per_sec:.1f} matmul ops/sec")
        
        if ops_per_sec < 100:
            print("  ⚠️  Performance seems low. Check GPU usage with nvidia-smi")
        
        return True
        
    except ImportError:
        print("✗ PyTorch not installed")
        print("  Install: pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121")
        return False
    except Exception as e:
        print(f"✗ Error checking PyTorch: {e}")
        return False


def check_ultralytics() -> bool:
    """Check Ultralytics YOLO."""
    print_subheader("Ultralytics YOLO")
    
    try:
        import ultralytics
        print(f"✓ Ultralytics version: {ultralytics.__version__}")
        
        # Try to import key components
        from ultralytics import YOLO
        print("✓ YOLO class imports successfully")
        
        return True
        
    except ImportError:
        print("✗ Ultralytics not installed")
        print("  Install: pip install ultralytics")
        return False
    except Exception as e:
        print(f"✗ Error checking Ultralytics: {e}")
        return False


def check_pyside6() -> bool:
    """Check PySide6 for GUI."""
    print_subheader("PySide6 (GUI Framework)")
    
    try:
        from PySide6 import QtWidgets, QtCore
        from PySide6.QtCore import QT_VERSION_STR
        print(f"✓ PySide6 version: {QT_VERSION_STR}")
        print("✓ QtWidgets imports successfully")
        return True
        
    except ImportError:
        print("✗ PySide6 not installed")
        print("  Install: pip install PySide6")
        return False
    except Exception as e:
        print(f"✗ Error checking PySide6: {e}")
        return False


def check_opencv() -> bool:
    """Check OpenCV."""
    print_subheader("OpenCV")
    
    try:
        import cv2
        print(f"✓ OpenCV version: {cv2.__version__}")
        
        # Check for CUDA support (optional, not critical)
        cuda_enabled = cv2.cuda.getCudaEnabledDeviceCount() > 0 if hasattr(cv2, 'cuda') else False
        if cuda_enabled:
            print("✓ OpenCV built with CUDA support")
        else:
            print("  ℹ️  OpenCV without CUDA (not critical for training)")
        
        return True
        
    except ImportError:
        print("✗ OpenCV not installed")
        print("  Install: pip install opencv-contrib-python")
        return False
    except Exception as e:
        print(f"✗ Error checking OpenCV: {e}")
        return False


def check_other_deps() -> bool:
    """Check other dependencies."""
    print_subheader("Other Dependencies")
    
    deps = {
        'numpy': 'NumPy',
        'PIL': 'Pillow',
        'yaml': 'PyYAML',
    }
    
    all_ok = True
    for module, name in deps.items():
        try:
            mod = __import__(module)
            version = getattr(mod, '__version__', 'unknown')
            print(f"✓ {name}: {version}")
        except ImportError:
            print(f"✗ {name} not installed")
            all_ok = False
    
    return all_ok


def check_training_app() -> bool:
    """Check if training app can be imported."""
    print_subheader("Training Application")
    
    try:
        # Add src to path if not already there
        src_path = Path(__file__).parent / 'src'
        if src_path.exists() and str(src_path) not in sys.path:
            sys.path.insert(0, str(src_path))
        
        from svo_handler.training_app import TrainingApp
        print("✓ Training app imports successfully")
        return True
        
    except ImportError as e:
        print(f"✗ Training app import failed: {e}")
        print("  Make sure you're in the SVO2-Handler directory")
        return False
    except Exception as e:
        print(f"✗ Error importing training app: {e}")
        return False


def check_dataset() -> bool:
    """Check if dataset exists (optional)."""
    print_subheader("Dataset (Optional)")
    
    possible_paths = [
        Path.cwd() / "YoloTraining-1.Iteration",
        Path.cwd() / "yolo_training",
        Path.home() / "YoloTraining-1.Iteration",
    ]
    
    for path in possible_paths:
        if path.exists():
            # Count subdirectories (buckets)
            buckets = [d for d in path.iterdir() if d.is_dir()]
            print(f"✓ Dataset found: {path}")
            print(f"  Buckets: {len(buckets)}")
            return True
    
    print("  ℹ️  Dataset not found (transfer from Jetson if needed)")
    print("  Expected location: ./YoloTraining-1.Iteration/")
    return True  # Not critical, just informational


def main() -> int:
    """Run all checks."""
    print_header("SVO2 Handler PC Training Environment Verification")
    print("\nThis script verifies your PC is ready for YOLO training.")
    print("Run this AFTER following docs/pc-setup-guide.md")
    
    checks = [
        ("Python", check_python),
        ("PyTorch + CUDA", check_torch),
        ("Ultralytics", check_ultralytics),
        ("PySide6", check_pyside6),
        ("OpenCV", check_opencv),
        ("Other Dependencies", check_other_deps),
        ("Training Application", check_training_app),
        ("Dataset", check_dataset),
    ]
    
    results = {}
    for name, check_fn in checks:
        try:
            results[name] = check_fn()
        except Exception as e:
            print(f"\n✗ Unexpected error in {name} check: {e}")
            results[name] = False
    
    # Summary
    print_header("Summary")
    
    critical_checks = ["Python", "PyTorch + CUDA", "Ultralytics", "PySide6", "OpenCV", "Other Dependencies"]
    critical_passed = all(results.get(name, False) for name in critical_checks)
    
    print("\nCritical Checks:")
    for name in critical_checks:
        status = "✓" if results.get(name, False) else "✗"
        print(f"  {status} {name}")
    
    print("\nOptional Checks:")
    optional = [name for name in results if name not in critical_checks]
    for name in optional:
        status = "✓" if results.get(name, False) else "ℹ️"
        print(f"  {status} {name}")
    
    print("\n" + "=" * 70)
    if critical_passed:
        print("✓ ALL CRITICAL CHECKS PASSED!")
        print("\nYou're ready to train. Launch with:")
        print("  python -m svo_handler.training_app")
    else:
        print("✗ SOME CHECKS FAILED")
        print("\nSee error messages above and:")
        print("  1. Follow docs/pc-setup-guide.md")
        print("  2. Install missing dependencies")
        print("  3. Run this script again")
    print("=" * 70)
    
    return 0 if critical_passed else 1


if __name__ == "__main__":
    sys.exit(main())
