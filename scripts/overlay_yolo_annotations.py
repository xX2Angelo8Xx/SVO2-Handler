#!/usr/bin/env python3
"""
Overlay Tool for Post-Benchmark Annotation

This utility reads YOLO .txt annotation files and overlays them on saved frames.
Use this after running a benchmark with "Save annotations only" mode.

Usage:
    python scripts/overlay_yolo_annotations.py <input_dir> <output_dir>

The input_dir should contain:
    - frame_NNNNNN.txt files (YOLO annotations)
    - Optionally: corresponding .jpg images (if not, provide --images_dir)

The tool will create annotated images in output_dir.
"""

import argparse
import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple
import sys


def parse_yolo_annotation(txt_path: Path, img_width: int, img_height: int) -> List[dict]:
    """
    Parse YOLO format annotation file.
    
    Args:
        txt_path: Path to .txt file with YOLO annotations
        img_width: Image width in pixels
        img_height: Image height in pixels
    
    Returns:
        List of detections with bbox coordinates and class
    """
    detections = []
    
    if not txt_path.exists() or txt_path.stat().st_size == 0:
        return detections  # Empty file or no detections
    
    with open(txt_path, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            
            class_id = int(parts[0])
            center_x = float(parts[1])
            center_y = float(parts[2])
            width = float(parts[3])
            height = float(parts[4])
            
            # Convert normalized YOLO format to pixel coordinates
            x1 = int((center_x - width / 2) * img_width)
            y1 = int((center_y - height / 2) * img_height)
            x2 = int((center_x + width / 2) * img_width)
            y2 = int((center_y + height / 2) * img_height)
            
            detections.append({
                'class': class_id,
                'bbox': (x1, y1, x2, y2)
            })
    
    return detections


def overlay_annotations(img: np.ndarray, detections: List[dict]) -> np.ndarray:
    """
    Draw YOLO detections on image.
    
    Args:
        img: BGR image
        detections: List of detection dictionaries
    
    Returns:
        Annotated image
    """
    annotated = img.copy()
    
    for det in detections:
        x1, y1, x2, y2 = det['bbox']
        class_id = det['class']
        
        # Color: Green for class 0 (target_close), Red for class 1 (target_far)
        color = (0, 255, 0) if class_id == 0 else (0, 0, 255)
        
        # Draw bounding box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        
        # Draw label
        label = "target_close" if class_id == 0 else "target_far"
        label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
        cv2.rectangle(annotated, (x1, y1 - 25), (x1 + label_size[0], y1), color, -1)
        cv2.putText(annotated, label, (x1, y1 - 5), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    return annotated


def process_directory(input_dir: Path, output_dir: Path, images_dir: Path = None,
                     frame_pattern: str = "frame_*.txt"):
    """
    Process all annotation files in directory.
    
    Args:
        input_dir: Directory containing .txt annotation files
        output_dir: Directory to save annotated images
        images_dir: Optional directory containing source images (if different from input_dir)
        frame_pattern: Pattern to match annotation files
    """
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Find all annotation files
    txt_files = sorted(input_dir.glob(frame_pattern))
    
    if not txt_files:
        print(f"❌ No annotation files found matching '{frame_pattern}' in {input_dir}")
        return
    
    print(f"📋 Found {len(txt_files)} annotation files")
    
    # Determine image directory
    if images_dir is None:
        images_dir = input_dir
    
    # Process each annotation file
    processed = 0
    skipped = 0
    
    for txt_file in txt_files:
        # Find corresponding image
        frame_name = txt_file.stem  # e.g., "frame_000123"
        img_path = images_dir / f"{frame_name}.jpg"
        
        if not img_path.exists():
            # Try alternative extensions
            for ext in ['.png', '.jpeg', '.bmp']:
                alt_path = images_dir / f"{frame_name}{ext}"
                if alt_path.exists():
                    img_path = alt_path
                    break
        
        if not img_path.exists():
            print(f"⚠️  Skipping {frame_name}: image not found")
            skipped += 1
            continue
        
        # Load image
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"⚠️  Skipping {frame_name}: failed to load image")
            skipped += 1
            continue
        
        # Parse annotations
        img_height, img_width = img.shape[:2]
        detections = parse_yolo_annotation(txt_file, img_width, img_height)
        
        # Overlay annotations
        annotated = overlay_annotations(img, detections)
        
        # Save annotated image
        output_path = output_dir / f"{frame_name}.jpg"
        cv2.imwrite(str(output_path), annotated)
        
        processed += 1
        
        # Progress update
        if processed % 100 == 0:
            print(f"  Processed {processed}/{len(txt_files)} frames...")
    
    print(f"\n✅ Complete!")
    print(f"   Processed: {processed} frames")
    print(f"   Skipped: {skipped} frames")
    print(f"   Output: {output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="Overlay YOLO annotations on saved frames",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Annotations and images in same directory
  python scripts/overlay_yolo_annotations.py benchmark_output/frames annotated_output

  # Annotations and images in separate directories
  python scripts/overlay_yolo_annotations.py benchmark_output/frames annotated_output --images_dir svo_frames

  # Custom frame pattern
  python scripts/overlay_yolo_annotations.py annotations/ output/ --pattern "detection_*.txt"
        """
    )
    
    parser.add_argument('input_dir', type=Path,
                       help='Directory containing YOLO .txt annotation files')
    parser.add_argument('output_dir', type=Path,
                       help='Directory to save annotated images')
    parser.add_argument('--images_dir', type=Path, default=None,
                       help='Directory containing source images (if different from input_dir)')
    parser.add_argument('--pattern', type=str, default='frame_*.txt',
                       help='Pattern to match annotation files (default: frame_*.txt)')
    
    args = parser.parse_args()
    
    # Validate input directory
    if not args.input_dir.exists():
        print(f"❌ Error: Input directory not found: {args.input_dir}")
        sys.exit(1)
    
    # Validate images directory if specified
    if args.images_dir and not args.images_dir.exists():
        print(f"❌ Error: Images directory not found: {args.images_dir}")
        sys.exit(1)
    
    print("=" * 70)
    print("YOLO ANNOTATION OVERLAY TOOL")
    print("=" * 70)
    print(f"Input dir:  {args.input_dir}")
    print(f"Images dir: {args.images_dir or args.input_dir}")
    print(f"Output dir: {args.output_dir}")
    print(f"Pattern:    {args.pattern}")
    print("=" * 70)
    print()
    
    # Process directory
    process_directory(args.input_dir, args.output_dir, args.images_dir, args.pattern)


if __name__ == '__main__':
    main()
