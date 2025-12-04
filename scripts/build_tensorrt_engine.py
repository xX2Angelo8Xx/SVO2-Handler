#!/usr/bin/env python3
"""
Build TensorRT engine from YOLO model for Jetson deployment.

This script converts ONNX models to optimized TensorRT engines for the Jetson.
Must be run ON THE JETSON to optimize for that specific hardware.

Usage:
    python build_tensorrt_engine.py <model_export_folder>
    
Example:
    python build_tensorrt_engine.py /media/angelo/DRONE_DATA1/JetsonExport/svo_model_20251204_112709_640/
"""

import argparse
import sys
import time
from pathlib import Path


def find_onnx_model(export_folder: Path) -> Path:
    """Find ONNX model in export folder."""
    models_dir = export_folder / "models"
    if not models_dir.exists():
        raise FileNotFoundError(f"Models directory not found: {models_dir}")
    
    onnx_files = list(models_dir.glob("*.onnx"))
    if not onnx_files:
        raise FileNotFoundError(f"No ONNX model found in {models_dir}")
    
    if len(onnx_files) > 1:
        print(f"⚠️  Multiple ONNX files found, using: {onnx_files[0].name}")
    
    return onnx_files[0]


def build_tensorrt_engine(
    onnx_path: Path,
    output_path: Path,
    fp16: bool = True,
    workspace: int = 4,
    verbose: bool = True
) -> bool:
    """
    Build TensorRT engine from ONNX model.
    
    Args:
        onnx_path: Path to ONNX model file
        output_path: Path for output .engine file
        fp16: Enable FP16 precision (faster, slightly less accurate)
        workspace: Max workspace size in GB
        verbose: Print detailed build log
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ Ultralytics not installed")
        print("   Install: pip install ultralytics")
        return False
    
    print("=" * 70)
    print("TensorRT Engine Builder")
    print("=" * 70)
    print(f"ONNX Model: {onnx_path}")
    print(f"Output: {output_path}")
    print(f"FP16: {fp16}")
    print(f"Workspace: {workspace}GB")
    print("=" * 70)
    print()
    
    # Check if TensorRT is available
    try:
        import tensorrt as trt
        print(f"✓ TensorRT version: {trt.__version__}")
    except ImportError:
        print("❌ TensorRT not found")
        print("   TensorRT should be included with JetPack")
        print("   Check: python3 -c 'import tensorrt; print(tensorrt.__version__)'")
        return False
    
    # Check if running on Jetson
    jetson_check = Path("/etc/nv_tegra_release")
    if jetson_check.exists():
        with open(jetson_check) as f:
            print(f"✓ Running on Jetson: {f.read().strip()}")
    else:
        print("⚠️  Not running on Jetson - engine may not be optimal")
        response = input("Continue anyway? [y/N]: ")
        if response.lower() != 'y':
            return False
    
    print()
    print("🔨 Building TensorRT engine...")
    print("   This may take 5-15 minutes depending on model size")
    print("   The Jetson may appear unresponsive - this is normal")
    print()
    
    start_time = time.time()
    
    try:
        # Load model
        model = YOLO(str(onnx_path))
        
        # Export to TensorRT
        # Ultralytics will automatically build the engine
        model.export(
            format="engine",
            imgsz=None,  # Use model's native size
            half=fp16,
            workspace=workspace,
            verbose=verbose
        )
        
        elapsed = time.time() - start_time
        
        print()
        print("=" * 70)
        print(f"✓ TensorRT engine built successfully in {elapsed:.1f}s")
        
        # Find generated engine file
        engine_path = onnx_path.with_suffix('.engine')
        if engine_path.exists():
            size_mb = engine_path.stat().st_size / 1024 / 1024
            print(f"✓ Engine file: {engine_path}")
            print(f"✓ Size: {size_mb:.1f} MB")
            
            # Move to output location if different
            if output_path != engine_path:
                engine_path.rename(output_path)
                print(f"✓ Moved to: {output_path}")
        else:
            print(f"⚠️  Engine file not found at expected location: {engine_path}")
            print(f"   Check models/ directory for .engine files")
        
        print("=" * 70)
        print()
        print("Next steps:")
        print("  1. Test inference: python test_inference.py <test_image>")
        print("  2. Run benchmark: python -m svo_handler.benchmark_app")
        print("  3. Compare PyTorch vs TensorRT performance")
        print()
        
        return True
        
    except Exception as e:
        print()
        print("=" * 70)
        print(f"❌ TensorRT build failed: {e}")
        print("=" * 70)
        
        if "out of memory" in str(e).lower():
            print()
            print("Out of memory error - try these solutions:")
            print("  1. Close other applications")
            print("  2. Reduce workspace size: --workspace 2")
            print("  3. Disable FP16: --no-fp16")
            print("  4. Reboot Jetson and try again")
        
        return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Build TensorRT engine from YOLO model for Jetson",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build with default settings (FP16, 4GB workspace)
  python build_tensorrt_engine.py /path/to/svo_model_folder/
  
  # Build with custom settings
  python build_tensorrt_engine.py /path/to/svo_model_folder/ --workspace 2 --no-fp16
  
  # Build from specific ONNX file
  python build_tensorrt_engine.py --onnx-path /path/to/model.onnx --output /path/to/output.engine
"""
    )
    
    parser.add_argument(
        "export_folder",
        type=Path,
        nargs="?",
        help="Model export folder (contains models/ subdirectory)"
    )
    
    parser.add_argument(
        "--onnx-path",
        type=Path,
        help="Direct path to ONNX model file (alternative to export_folder)"
    )
    
    parser.add_argument(
        "--output",
        type=Path,
        help="Output path for .engine file (default: same as ONNX with .engine extension)"
    )
    
    parser.add_argument(
        "--no-fp16",
        action="store_true",
        help="Disable FP16 precision (use FP32, slower but more accurate)"
    )
    
    parser.add_argument(
        "--workspace",
        type=int,
        default=4,
        help="Max workspace size in GB (default: 4)"
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed build log"
    )
    
    args = parser.parse_args()
    
    # Determine ONNX path
    if args.onnx_path:
        onnx_path = args.onnx_path
        if not onnx_path.exists():
            print(f"❌ ONNX file not found: {onnx_path}")
            return 1
    elif args.export_folder:
        try:
            onnx_path = find_onnx_model(args.export_folder)
        except FileNotFoundError as e:
            print(f"❌ {e}")
            return 1
    else:
        parser.print_help()
        return 1
    
    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = onnx_path.with_suffix('.engine')
    
    # Build engine
    success = build_tensorrt_engine(
        onnx_path=onnx_path,
        output_path=output_path,
        fp16=not args.no_fp16,
        workspace=args.workspace,
        verbose=args.verbose
    )
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
