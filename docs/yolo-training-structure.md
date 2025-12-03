# YOLO Training Structure

Complete specification of the bucket organization, numeric prefixes, filename conventions, and class definitions for the YOLO training dataset.

---

## Overview

The training dataset uses a **72-bucket + 1 far bucket** structure to ensure balanced viewpoint distribution for robust YOLO model training. This organization enforces consistent representation across:
- **Directions**: 8 cardinal directions for trajectory-aware detection
- **Positions**: 3 vertical frame positions (bot/horizon/top)
- **Distances**: 3 depth ranges based on ZED sensor capability

---

## Bucket Structure

### Root Directory
```
/media/angelo/DRONE_DATA1/YoloTrainingV1/
```

### Directory Hierarchy

```
YoloTrainingV1/
├── 0_far/                    # target_far images (beyond sensor range)
│   ├── frame_000123-FlightA-far.jpg
│   ├── frame_000123-FlightA-far.txt
│   └── ...
├── 1_S/                      # South direction
│   ├── Bot/                  # Bottom of frame
│   │   ├── near/             # <10m
│   │   ├── mid/              # 10-30m
│   │   └── far/              # >30m or no depth
│   ├── Horizon/              # Middle of frame
│   │   ├── near/
│   │   ├── mid/
│   │   └── far/
│   └── Top/                  # Top of frame
│       ├── near/
│       ├── mid/
│       └── far/
├── 2_SE/                     # Southeast direction
│   ├── Bot/
│   │   ├── near/
│   │   ├── mid/
│   │   └── far/
│   └── ...
├── 3_E/                      # East direction
├── 4_NE/                     # Northeast direction
├── 5_N/                      # North direction
├── 6_NW/                     # Northwest direction
├── 7_W/                      # West direction
└── 8_SW/                     # Southwest direction
```

**Total buckets**: 1 (far) + 8 (directions) × 3 (positions) × 3 (distances) = **73 buckets**

---

## Numeric Prefixes

### Purpose
- Enforce consistent alphabetical ordering
- Simplify programmatic bucket iteration
- Distinguish `0_far` (special case) from directional buckets

### Mapping

| Prefix | Direction | Description |
|--------|-----------|-------------|
| `0` | far | Beyond sensor range (no direction) |
| `1` | S | South |
| `2` | SE | Southeast |
| `3` | E | East |
| `4` | NE | Northeast |
| `5` | N | North |
| `6` | NW | Northwest |
| `7` | W | West |
| `8` | SW | Southwest |

### Code Reference
```python
# From src/svo_handler/training_export.py
DIRECTION_PREFIXES = {
    "far": "0_far",
    "S": "1_S",
    "SE": "2_SE",
    "E": "3_E",
    "NE": "4_NE",
    "N": "5_N",
    "NW": "6_NW",
    "W": "7_W",
    "SW": "8_SW"
}
```

---

## YOLO Classes

### Class Definitions

| Class ID | Class Name | Description | Depth Range | Purpose |
|----------|------------|-------------|-------------|---------|
| 0 | `target_close` | Target within sensor range | 0-40m | High-confidence detection with depth |
| 1 | `target_far` | Target beyond sensor range | >40m or unreliable | Low-confidence detection, no depth |

### Class Selection Logic

**target_close (class 0)**:
- Target is within ZED2i sensor effective range (0-40m)
- Has reliable depth data from sensor
- Exported to full 72-bucket structure (direction/position/distance)
- Filename includes depth statistics
- Training focuses on accurate localization + depth estimation

**target_far (class 1)**:
- Target beyond sensor range (>40m)
- Depth data missing, unreliable, or all invalid values
- Exported to simplified `0_far/` bucket (no sub-buckets)
- Filename simplified (no direction/position metadata)
- Training focuses on detection only, not depth

### Rationale
- **Two-tier confidence**: Model learns which detections are depth-reliable
- **Sensor limitations**: ZED2i depth accuracy degrades beyond ~40m
- **Training efficiency**: Separate handling prevents mixed-quality data
- **Deployment ready**: Inference can prioritize target_close for navigation decisions

---

## Bucket Dimensions

### 1. Direction (8 Cardinal + 1 Far)

#### Purpose
Enforce trajectory-aware detection for drone interception scenarios.

#### Definitions
- **S (South)**: Target south of drone (behind in typical flight)
- **SE (Southeast)**: Southeastern quadrant
- **E (East)**: Target east of drone (right side)
- **NE (Northeast)**: Northeastern quadrant
- **N (North)**: Target north of drone (ahead in typical flight)
- **NW (Northwest)**: Northwestern quadrant
- **W (West)**: Target west of drone (left side)
- **SW (Southwest)**: Southwestern quadrant
- **far**: Beyond sensor range (no reliable direction)

#### Selection Guide
Based on drone heading and target relative position. If drone heading is known:
- Calculate relative bearing to target
- Map to nearest cardinal direction
- For ambiguous cases (e.g., exactly between N and NE), choose based on consistency

### 2. Position (3 Vertical)

#### Purpose
Ensure model handles targets at different vertical frame positions (important for pitch angle and altitude differences).

#### Definitions
- **Bot**: Target in bottom third of frame
  - Target below drone (or frame pitched down)
  - Typical for ground-level pursuit or descending
- **Horizon**: Target in middle third of frame
  - Level flight, target at similar altitude
  - Most common in cruise scenarios
- **Top**: Target in top third of frame
  - Target above drone (or frame pitched up)
  - Typical for climbing pursuit or target at higher altitude

#### Selection Guide
Divide frame vertically into thirds:
```
Top:     y ∈ [0, height/3)
Horizon: y ∈ [height/3, 2*height/3)
Bot:     y ∈ [2*height/3, height]
```
Use bbox center y-coordinate to determine position.

### 3. Distance (3 Ranges)

#### Purpose
Balance close-range (large targets) and far-range (small targets) for scale-invariant detection.

#### Definitions
- **near**: <10m
  - Close-range engagements
  - Large targets in frame
  - High depth accuracy
- **mid**: 10-30m
  - Medium-range scenarios
  - Moderate target size
  - Good depth accuracy
- **far**: >30m or no valid depth
  - Long-range detection
  - Small targets
  - Depth accuracy degrades

#### Selection Guide
Use mean depth from bbox statistics:
```python
if mean_depth < 10.0:
    distance = "near"
elif mean_depth <= 30.0:
    distance = "mid"
else:
    distance = "far"
```

**Note**: If depth data is invalid or unreliable for the entire bbox, default to `far` distance bucket within target_close, or use target_far class if beyond sensor range entirely.

---

## Filename Conventions

### target_close (class 0) WITH Depth Data

**Pattern**:
```
frame_NNNNNN-<source_folder>-<DIR>_<POS>-depth-XX.XXm-std-X.XXm.jpg
```

**Example**:
```
frame_000123-Flight001_20231115-1_S_Bot-depth-12.45m-std-2.13m.jpg
```

**Components**:
- `frame_000123`: Original frame number (6-digit zero-padded)
- `Flight001_20231115`: Source folder name (tracks which flight/recording)
- `1_S`: Direction with numeric prefix (South)
- `Bot`: Position (bottom of frame)
- `depth-12.45m`: Mean depth within bbox (2 decimal places)
- `std-2.13m`: Standard deviation of depth within bbox (2 decimal places)

### target_close (class 0) WITHOUT Depth Data (Manual Entry)

**Pattern**:
```
frame_NNNNNN-<source_folder>-<DIR>_<POS>-depth-XX.XXm-std-0.00m.jpg
```

**Example**:
```
frame_000456-Flight002_20231116-4_NE_Horizon-depth-25.00m-std-0.00m.jpg
```

**Note**: `std-0.00m` indicates manually entered depth, not sensor-derived.

### target_far (class 1)

**Pattern**:
```
frame_NNNNNN-<source_folder>-far.jpg
```

**Example**:
```
frame_000789-Flight003_20231117-far.jpg
```

**Simplified**: No direction/position metadata since target is too distant for reliable characterization.

---

## YOLO Label Format

### File Structure
Each `.jpg` has corresponding `.txt` with same base name:
```
frame_000123-Flight001-1_S_Bot-depth-12.45m-std-2.13m.jpg
frame_000123-Flight001-1_S_Bot-depth-12.45m-std-2.13m.txt
```

### Label Content (YOLO Format)
```
<class_id> <x_center> <y_center> <width> <height>
```

**Normalized coordinates** (0.0 to 1.0):
- `class_id`: 0 (target_close) or 1 (target_far)
- `x_center`: Bbox center X / image width
- `y_center`: Bbox center Y / image height
- `width`: Bbox width / image width
- `height`: Bbox height / image height

**Example**:
```
0 0.5234 0.3891 0.1203 0.0854
```
Interpretation: target_close at center (52.34%, 38.91%) with size (12.03%, 8.54%)

---

## Bucket Balance Guidelines

### Ideal Distribution
For robust training, aim for balanced representation across all buckets.

**Target counts per bucket** (example for dataset of 1000 images):
- Each directional bucket: ~125 images (1000 / 8 directions)
- Each position within direction: ~42 images (125 / 3 positions)
- Each distance within position: ~14 images (42 / 3 distances)

### Monitoring Balance
Use Annotation Checker's statistics feature:
```bash
python -m svo_handler.checker_app
# Select direction "1_S", mode "All"
# Check stats: "Gesamt: 125 Bilder (Bot/near: 15, Bot/mid: 12, Bot/far: 10, ...)"
```

### Addressing Imbalances

**Underrepresented buckets**:
- Review existing flight recordings for matching scenarios
- Prioritize annotation of frames with targets in sparse buckets
- Consider capturing additional flight data for missing viewpoints

**Overrepresented buckets**:
- Use data augmentation carefully (don't amplify imbalances)
- Consider stratified sampling during training split

---

## Training Dataset Splits

### Recommended Split
- **Train**: 70-80% of images
- **Validation**: 10-15% of images
- **Test**: 10-15% of images

### Split Strategy

**Option 1: Stratified by bucket**
- Ensure each bucket represented proportionally in all splits
- Preserves viewpoint balance in train/val/test
- **Recommended** for balanced training

**Option 2: Stratified by source folder**
- Split by flight/recording (all frames from flight X in same split)
- Prevents temporal leakage (similar consecutive frames in train+val)
- Tests generalization to new flight conditions

**Hybrid approach** (best):
1. Group by source folder
2. Split folders into train/val/test
3. Verify bucket balance within each split
4. Adjust if severe imbalance detected

---

## CSV Annotation Log

### Purpose
Track all exported annotations with metadata for analysis and debugging.

### Location
```
<training_root>/annotations.csv
```

### Format
```csv
timestamp,source_folder,frame_number,class,direction,position,distance,mean_depth,std_depth,bbox_x,bbox_y,bbox_w,bbox_h,filename
2024-11-15T14:23:01,Flight001,000123,target_close,1_S,Bot,near,12.45,2.13,234,456,120,85,frame_000123-Flight001-1_S_Bot-depth-12.45m-std-2.13m.jpg
2024-11-15T14:23:15,Flight001,000124,target_far,0_far,,,,,237,460,125,88,frame_000124-Flight001-far.jpg
```

### Columns
- `timestamp`: Export time (ISO 8601)
- `source_folder`: Originating flight/recording
- `frame_number`: Frame index within source
- `class`: target_close or target_far
- `direction`: Numeric prefix + direction (e.g., 1_S)
- `position`: Bot, Horizon, Top (empty for target_far)
- `distance`: near, mid, far (empty for target_far)
- `mean_depth`: Mean depth in meters (empty for target_far)
- `std_depth`: Depth standard deviation (empty for target_far)
- `bbox_x`, `bbox_y`, `bbox_w`, `bbox_h`: Pixel coordinates
- `filename`: Full filename in training bucket

### Usage
```python
import pandas as pd

# Load annotations
df = pd.read_csv('annotations.csv')

# Count by bucket
bucket_counts = df.groupby(['direction', 'position', 'distance']).size()

# Find underrepresented buckets
sparse = bucket_counts[bucket_counts < 10]

# Check source folder distribution
flight_counts = df.groupby('source_folder').size()
```

---

## Directory Management

### Automatic Bucket Creation
Buckets created on first export to that category:
```python
# From src/svo_handler/training_export.py
def ensure_bucket_structure(training_root: Path, direction: str) -> None:
    """Create bucket directories if they don't exist."""
    dir_path = training_root / DIRECTION_PREFIXES[direction]
    
    if direction == "far":
        dir_path.mkdir(parents=True, exist_ok=True)
    else:
        for position in POSITIONS:
            for distance in DISTANCES:
                bucket = dir_path / position / distance
                bucket.mkdir(parents=True, exist_ok=True)
```

### Safety Measures
- **No overwrite**: Existing buckets never deleted automatically
- **Duplicate check**: Warns before overwriting existing annotation
- **Validation**: Checks write permissions before export

---

## Code Reference

### Key Constants
```python
# From src/svo_handler/training_export.py

DIRECTIONS = ["S", "SE", "E", "NE", "N", "NW", "W", "SW", "far"]

DIRECTION_PREFIXES = {
    "far": "0_far",
    "S": "1_S",
    "SE": "2_SE",
    "E": "3_E",
    "NE": "4_NE",
    "N": "5_N",
    "NW": "6_NW",
    "W": "7_W",
    "SW": "8_SW"
}

POSITIONS = ["Bot", "Horizon", "Top"]

DISTANCES = ["near", "mid", "far"]
```

### Bucket Path Construction
```python
def get_target_bucket(
    training_root: Path,
    yolo_class: str,
    direction: str,
    position: str,
    distance: str
) -> Path:
    """Construct full bucket path."""
    if yolo_class == "target_far":
        return training_root / "0_far"
    else:
        dir_prefix = DIRECTION_PREFIXES[direction]
        return training_root / dir_prefix / position / distance
```

---

## Best Practices

### Annotation Phase
1. ✅ **Review depth data** before classifying (target_close vs target_far)
2. ✅ **Use consistent direction** mapping (define North as drone forward heading)
3. ✅ **Check bbox fully contains target** with minimal excess background
4. ✅ **Verify position** by bbox center Y-coordinate
5. ✅ **Let depth determine distance** automatically (don't override unless necessary)

### Dataset Assembly
1. ✅ **Monitor bucket balance** regularly with Checker app statistics
2. ✅ **Prioritize underrepresented** buckets when annotating new flights
3. ✅ **Track source folders** to ensure diverse flight conditions
4. ✅ **Use CSV log** for analysis and debugging
5. ✅ **Verify splits** maintain bucket balance before training

### Quality Assurance
1. ✅ **Spot-check random** samples per bucket, not just first images
2. ✅ **Verify bucket overlay** matches actual image content in Checker
3. ✅ **Cross-reference CSV** if bucket counts seem inconsistent
4. ✅ **Review target_far** for targets that should be target_close (sensor range edge cases)
5. ✅ **Check for duplicates** across buckets (same frame in multiple locations)

---

## Troubleshooting

### Missing Buckets
**Problem**: Expected bucket doesn't exist  
**Cause**: No annotations exported to that category yet  
**Solution**: Annotate frames matching that viewpoint, export creates bucket automatically

### Imbalanced Buckets
**Problem**: Some buckets have 100+ images, others <5  
**Cause**: Flight conditions/annotations favor certain viewpoints  
**Solution**: Review CSV for underrepresented buckets, annotate matching frames from other flights

### Duplicate Frames
**Problem**: Same frame appears in multiple buckets (e.g., 1_S/Bot/near and 1_S/Horizon/near)  
**Cause**: Re-annotating same frame without checking existing exports  
**Solution**: Viewer warns on duplicate, delete incorrect annotation, keep correct one

### Wrong Bucket
**Problem**: target_close in `0_far/` or vice versa  
**Cause**: Misclassification during annotation  
**Solution**: Delete incorrect file, re-annotate with correct class

### Filename Mismatch
**Problem**: `.jpg` exists but no matching `.txt` (or vice versa)  
**Cause**: Export interrupted or filesystem error  
**Solution**: Delete orphaned file, re-export annotation

---

## Future Enhancements

### Planned Features
- **Auto-classification**: YOLO pre-annotation to speed up manual review
- **Augmentation pipeline**: Rotate, flip, brightness adjust within buckets
- **Balance enforcer**: Warn when bucket imbalance exceeds threshold
- **Merge tool**: Combine multiple training roots, deduplicate across datasets
- **Synthetic data**: Generate additional examples for sparse buckets via augmentation

### Configuration Flexibility
- **Customizable distance thresholds**: Adjust near/mid/far ranges per deployment
- **Additional positions**: Split Bot/Horizon/Top into 5 or more vertical bands
- **Finer directions**: Add intermediate directions (NNE, ENE, ESE, etc.)
- **Class expansion**: Add target_medium, target_occluded, etc.

---

## Summary

The YOLO training structure enforces a **balanced, organized, and scalable** approach to dataset assembly:

- **73 buckets**: Comprehensive viewpoint coverage
- **Numeric prefixes**: Consistent ordering and programmatic access
- **Two-tier classification**: Depth-reliable vs. detection-only targets
- **Rich metadata**: Filenames encode direction, position, depth for traceability
- **CSV logging**: Full audit trail for analysis
- **Safety features**: Duplicate detection, export-only workflow

This structure enables training of **trajectory-aware, depth-integrated YOLO models** optimized for drone interception scenarios.
