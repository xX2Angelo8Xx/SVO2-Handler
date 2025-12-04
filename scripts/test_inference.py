#!/usr/bin/env python3
"""
Test inference with trained YOLO model.

This script loads a YOLO model (.pt, .onnx, or .engine) and runs inference
on test images to verify the model works correctly.

Usage:
    python test_inference.py <model_path> <test_image_or_folder>
    
Examples:
    # Test with PyTorch model
    python test_inference.py models/best.pt test_images/frame_000001.jpg
    
    # Test with TensorRT engine
    python test_inference.py models/best.engine test_images/
    
    # Benchmark mode (no visualization)
    python test_inference.py models/best.engine test_images/ --benchmark --iterations 100
"""

import argparse
import sys
import time
from pathlib import Path
from typing import List

import cv2
import numpy as np


def load_model(model_path: Path, verbose: bool = True):
    """Load YOLO model from file."""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ Ultralytics not installed")
        print("   Install: pip install ultralytics")
        sys.exit(1)
    
    if verbose:
        print(f"Loading model: {model_path}")
    
    model = YOLO(str(model_path))
    
    if verbose:
        model_type = "TensorRT" if str(model_path).endswith('.engine') else \
                    "ONNX" if str(model_path).endswith('.onnx') else "PyTorch"
        print(f"✓ Model loaded ({model_type})")
    
    return model


def get_test_images(path: Path) -> List[Path]:
    """Get list of test images from path (file or directory)."""
    if path.is_file():
        return [path]
    elif path.is_dir():
        images = []
        for ext in ['*.jpg', '*.jpeg', '*.png']:
            images.extend(path.glob(ext))
        return sorted(images)
    else:
        raise FileNotFoundError(f"Test path not found: {path}")


def run_inference(
    model,
    image_path: Path,
    conf_threshold: float = 0.25,
    save_output: bool = True,
    verbose: bool = True
):
    """Run inference on a single image."""
    # Load image
    image = cv2.imread(str(image_path))
    if image is None:
        print(f"❌ Failed to load image: {image_path}")
        return None
    
    # Run inference
    start_time = time.time()
    results = model(image, conf=conf_threshold, verbose=False)
    inference_time = time.time() - start_time
    
    # Extract results
    result = results[0]
    boxes = result.boxes
    
    if verbose:
        print(f"\n{image_path.name}:")
        print(f"  Inference time: {inference_time*1000:.1f}ms ({1/inference_time:.1f} FPS)")
        print(f"  Detections: {len(boxes)}")
        
        if len(boxes) > 0:
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                class_name = "target_close" if cls == 0 else "target_far"
                print(f"    - {class_name}: {conf:.2f}")
    
    # Save annotated image
    if save_output and len(boxes) > 0:
        output_path = image_path.parent / f"{image_path.stem}_detected{image_path.suffix}"
        annotated = result.plot()  # Get annotated image
        cv2.imwrite(str(output_path), annotated)
        if verbose:
            print(f"  Saved: {output_path.name}")
    
    return {
        'image_path': image_path,
        'inference_time': inference_time,
        'detections': len(boxes),
        'boxes': boxes
    }


def run_benchmark(
    model,
    test_images: List[Path],
    iterations: int = 100,
    warmup: int = 10,
    conf_threshold: float = 0.25
):
    """Run benchmark on multiple images."""
    print("=" * 70)
    print("Benchmark Mode")
    print("=" * 70)
    print(f"Test images: {len(test_images)}")
    print(f"Warmup: {warmup} iterations")
    print(f"Benchmark: {iterations} iterations")
    print()
    
    # Warmup
    print("Warming up...")
    for i in range(warmup):
        img_idx = i % len(test_images)
        image = cv2.imread(str(test_images[img_idx]))
        _ = model(image, conf=conf_threshold, verbose=False)
    
    # Benchmark
    print(f"Running benchmark ({iterations} iterations)...")
    times = []
    
    for i in range(iterations):
        img_idx = i % len(test_images)
        image = cv2.imread(str(test_images[img_idx]))
        
        start = time.time()
        _ = model(image, conf=conf_threshold, verbose=False)
        elapsed = time.time() - start
        
        times.append(elapsed)
        
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i+1}/{iterations} ({(i+1)/iterations*100:.0f}%)")
    
    # Statistics
    times_ms = np.array(times) * 1000
    
    print()
    print("=" * 70)
    print("Benchmark Results")
    print("=" * 70)
    print(f"Iterations: {iterations}")
    print(f"Mean time: {times_ms.mean():.1f}ms")
    print(f"Std dev: {times_ms.std():.1f}ms")
    print(f"Min time: {times_ms.min():.1f}ms")
    print(f"Max time: {times_ms.max():.1f}ms")
    print(f"P50 (median): {np.percentile(times_ms, 50):.1f}ms")
    print(f"P95: {np.percentile(times_ms, 95):.1f}ms")
    print(f"P99: {np.percentile(times_ms, 99):.1f}ms")
    print()
    print(f"Mean FPS: {1/(times_ms.mean()/1000):.1f}")
    print(f"Peak FPS (min time): {1/(times_ms.min()/1000):.1f}")
    print("=" * 70)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test YOLO model inference",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "model",
        type=Path,
        help="Path to model file (.pt, .onnx, or .engine)"
    )
    
    parser.add_argument(
        "test_path",
        type=Path,
        help="Path to test image or folder of images"
    )
    
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Confidence threshold (default: 0.25)"
    )
    
    parser.add_argument(
        "--benchmark",
        action="store_true",
        help="Run benchmark mode (no visualization, compute stats)"
    )
    
    parser.add_argument(
        "--iterations",
        type=int,
        default=100,
        help="Number of benchmark iterations (default: 100)"
    )
    
    parser.add_argument(
        "--warmup",
        type=int,
        default=10,
        help="Number of warmup iterations (default: 10)"
    )
    
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save annotated images"
    )
    
    args = parser.parse_args()
    
    # Validate paths
    if not args.model.exists():
        print(f"❌ Model file not found: {args.model}")
        return 1
    
    if not args.test_path.exists():
        print(f"❌ Test path not found: {args.test_path}")
        return 1
    
    # Load model
    model = load_model(args.model, verbose=not args.benchmark)
    
    # Get test images
    test_images = get_test_images(args.test_path)
    if not test_images:
        print(f"❌ No test images found in: {args.test_path}")
        return 1
    
    if not args.benchmark:
        print(f"\nFound {len(test_images)} test image(s)")
        print()
    
    # Run inference or benchmark
    if args.benchmark:
        run_benchmark(
            model,
            test_images,
            iterations=args.iterations,
            warmup=args.warmup,
            conf_threshold=args.conf
        )
    else:
        # Run inference on each image
        for image_path in test_images:
            run_inference(
                model,
                image_path,
                conf_threshold=args.conf,
                save_output=not args.no_save,
                verbose=True
            )
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
