#!/usr/bin/env python3
"""
Benchmark scenarios for different testing phases.

Architecture:
- Modular scenario system
- Each scenario tests a specific pipeline component
- Results are comparable across scenarios
- Supports external algorithm plugins

Scenarios:
1. Pure Inference: TensorRT model only (current implementation)
2. SVO Pipeline: SVO2 → grab → inference → depth extraction
3. Tracking Pipeline: Full tracking with mathematical trackers
4. External Plugin: User-provided algorithms
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import time
import json


@dataclass
class BenchmarkResult:
    """Results from a benchmark scenario."""
    scenario_name: str
    total_time_seconds: float
    frames_processed: int
    mean_fps: float
    mean_latency_ms: float
    
    # Component timings
    component_times: Dict[str, float]  # e.g., {'grab': 5.2, 'inference': 12.3, 'depth': 8.1}
    
    # Detection/tracking metrics
    total_detections: int
    frames_with_detections: int
    
    # Optional tracking metrics
    tracking_metrics: Optional[Dict[str, Any]] = None
    
    # Memory usage
    peak_memory_mb: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return asdict(self)


class BenchmarkScenario(ABC):
    """Base class for benchmark scenarios."""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.results: Optional[BenchmarkResult] = None
    
    @abstractmethod
    def setup(self, config: Dict[str, Any]) -> bool:
        """
        Setup the scenario with configuration.
        
        Args:
            config: Scenario-specific configuration
            
        Returns:
            True if setup successful, False otherwise
        """
        pass
    
    @abstractmethod
    def run_frame(self, frame_data: Any) -> Dict[str, Any]:
        """
        Process a single frame.
        
        Args:
            frame_data: Input data (could be image path, SVO frame, etc.)
            
        Returns:
            Dictionary with frame results:
            {
                'detections': List of detections,
                'timings': Dict of component timings,
                'depth_data': Optional depth information,
                'tracking_info': Optional tracking state
            }
        """
        pass
    
    @abstractmethod
    def cleanup(self):
        """Cleanup resources after benchmark."""
        pass
    
    def benchmark(self, input_data: List[Any], 
                  progress_callback=None) -> BenchmarkResult:
        """
        Run full benchmark on input data.
        
        Args:
            input_data: List of inputs to process
            progress_callback: Optional callback(current, total, fps)
            
        Returns:
            BenchmarkResult with metrics
        """
        total = len(input_data)
        all_timings = {key: [] for key in ['grab', 'inference', 'depth', 'tracking']}
        total_detections = 0
        frames_with_detections = 0
        
        start_time = time.time()
        
        for idx, data in enumerate(input_data):
            frame_result = self.run_frame(data)
            
            # Accumulate timings
            for component, timing in frame_result.get('timings', {}).items():
                if component in all_timings:
                    all_timings[component].append(timing)
            
            # Count detections
            detections = frame_result.get('detections', [])
            total_detections += len(detections)
            if len(detections) > 0:
                frames_with_detections += 1
            
            # Progress callback
            if progress_callback:
                elapsed = time.time() - start_time
                current_fps = (idx + 1) / elapsed if elapsed > 0 else 0
                progress_callback(idx + 1, total, current_fps)
        
        total_time = time.time() - start_time
        mean_fps = total / total_time if total_time > 0 else 0
        mean_latency = (total_time / total) * 1000 if total > 0 else 0
        
        # Calculate mean component times
        component_means = {
            key: sum(times) / len(times) if times else 0.0
            for key, times in all_timings.items()
        }
        
        self.results = BenchmarkResult(
            scenario_name=self.name,
            total_time_seconds=total_time,
            frames_processed=total,
            mean_fps=mean_fps,
            mean_latency_ms=mean_latency,
            component_times=component_means,
            total_detections=total_detections,
            frames_with_detections=frames_with_detections
        )
        
        return self.results


class PureInferenceScenario(BenchmarkScenario):
    """
    Scenario 1: Pure TensorRT inference on pre-loaded images.
    Current implementation - baseline performance.
    """
    
    def __init__(self):
        super().__init__(
            "Pure Inference",
            "TensorRT model inference only (baseline)"
        )
        self.model = None
        self.conf_threshold = 0.25
    
    def setup(self, config: Dict[str, Any]) -> bool:
        """Setup model."""
        try:
            from ultralytics import YOLO
            model_path = config.get('model_path')
            self.conf_threshold = config.get('conf_threshold', 0.25)
            
            if not model_path or not Path(model_path).exists():
                return False
            
            self.model = YOLO(str(model_path))
            return True
        except Exception as e:
            print(f"Setup failed: {e}")
            return False
    
    def run_frame(self, frame_data: Any) -> Dict[str, Any]:
        """Run inference on image."""
        import cv2
        
        # frame_data is image path
        img = cv2.imread(str(frame_data))
        
        start = time.time()
        results = self.model(img, conf=self.conf_threshold, verbose=False)
        inference_time = (time.time() - start) * 1000  # ms
        
        detections = []
        for box in results[0].boxes:
            detections.append({
                'class': int(box.cls[0]),
                'confidence': float(box.conf[0]),
                'bbox': box.xyxy[0].tolist()
            })
        
        return {
            'detections': detections,
            'timings': {'inference': inference_time}
        }
    
    def cleanup(self):
        """Cleanup model."""
        self.model = None


class SVOPipelineScenario(BenchmarkScenario):
    """
    Scenario 2: Full SVO2 pipeline with depth extraction.
    
    Pipeline:
    1. Open SVO2 file with NEURAL_PLUS depth mode
    2. Wait for initialization (loading can take 30-60s)
    3. Process entire SVO2 file sequentially
    4. For each frame:
       - Grab left camera frame
       - Run YOLO inference
       - Extract depth ONLY in detection bounding box areas
       - Optionally save annotated images
    
    Tests real-world Jetson performance with depth extraction.
    """
    
    def __init__(self):
        super().__init__(
            "SVO Pipeline",
            "SVO2 grab → YOLO → Depth extraction in bbox (NEURAL_PLUS)"
        )
        self.camera = None
        self.model = None
        self.image = None
        self.depth = None
        self.runtime_params = None
        self.save_images = False
        self.output_dir = None
        self.frame_index = 0
        self.total_frames = 0
        self.loading_complete = False
        self.preview_callback = None
        self.loading_progress_callback = None
    
    def setup(self, config: Dict[str, Any]) -> bool:
        """
        Setup SVO and model.
        
        This method handles the initial loading phase which can take 30-60 seconds
        for NEURAL_PLUS depth mode initialization.
        
        Args:
            config: Dictionary with:
                - svo_path: Path to .svo2 file
                - model_path: Path to YOLO .engine model
                - conf_threshold: Detection confidence threshold
                - save_images: Whether to save annotated frames
                - save_annotations_only: Save only YOLO .txt files (fast)
                - output_dir: Directory for saved images (if save_images=True)
                - loading_progress_callback: Function to call with loading progress
                - preview_callback: Function to call with preview image
        
        Returns:
            True if setup successful, False otherwise
        """
        try:
            import pyzed.sl as sl
            from ultralytics import YOLO
            import time
            
            svo_path = config.get('svo_path')
            model_path = config.get('model_path')
            self.conf_threshold = config.get('conf_threshold', 0.25)
            self.save_images = config.get('save_images', False)
            self.save_annotations_only = config.get('save_annotations_only', False)
            self.output_dir = config.get('output_dir')
            self.preview_callback = config.get('preview_callback')
            self.loading_progress_callback = config.get('loading_progress_callback')
            
            if not svo_path or not model_path:
                return False
            
            # Create output directory if needed
            if (self.save_images or self.save_annotations_only) and self.output_dir:
                Path(self.output_dir).mkdir(parents=True, exist_ok=True)
            
            # Report loading start
            if self.loading_progress_callback:
                self.loading_progress_callback(0, "Initializing ZED camera...")
            
            # Initialize camera
            self.camera = sl.Camera()
            
            init_params = sl.InitParameters()
            init_params.set_from_svo_file(str(svo_path))
            init_params.depth_mode = sl.DEPTH_MODE.NEURAL_PLUS  # Best quality
            init_params.coordinate_units = sl.UNIT.METER
            init_params.depth_minimum_distance = 1.0  # 1 meter minimum
            init_params.depth_maximum_distance = 40.0  # 40 meters maximum
            
            if self.loading_progress_callback:
                self.loading_progress_callback(10, "Opening SVO2 file...")
            
            status = self.camera.open(init_params)
            if status != sl.ERROR_CODE.SUCCESS:
                print(f"Camera open failed: {status}")
                return False
            
            # Get total frame count
            self.total_frames = self.camera.get_svo_number_of_frames()
            
            if self.loading_progress_callback:
                self.loading_progress_callback(30, f"Loading NEURAL_PLUS depth (this takes 30-60s)...")
            
            # Do a test grab to trigger depth initialization
            # NEURAL_PLUS depth mode requires preprocessing that happens on first grab
            test_params = sl.RuntimeParameters()
            test_params.confidence_threshold = 50
            
            for i in range(3):  # Multiple grabs ensure full initialization
                if self.camera.grab(test_params) == sl.ERROR_CODE.SUCCESS:
                    if self.loading_progress_callback:
                        self.loading_progress_callback(30 + (i+1) * 15, "Initializing depth neural network...")
                    time.sleep(0.1)
            
            # Reset to start of SVO
            self.camera.set_svo_position(0)
            
            if self.loading_progress_callback:
                self.loading_progress_callback(80, "Loading YOLO model...")
            
            # Load YOLO model
            self.model = YOLO(str(model_path))
            
            if self.loading_progress_callback:
                self.loading_progress_callback(95, "Finalizing setup...")
            
            # Prepare image and depth containers
            self.image = sl.Mat()
            self.depth = sl.Mat()
            
            # Runtime parameters for grab
            self.runtime_params = sl.RuntimeParameters()
            self.runtime_params.confidence_threshold = 50
            
            self.frame_index = 0
            self.loading_complete = True
            
            if self.loading_progress_callback:
                self.loading_progress_callback(100, f"Ready! SVO has {self.total_frames} frames.")
            
            return True
            
        except Exception as e:
            print(f"Setup failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_frame(self, frame_data: Any) -> Dict[str, Any]:
        """
        Run full pipeline on next SVO frame.
        
        frame_data is ignored - we grab from SVO sequentially.
        Processes the entire SVO2 file frame by frame.
        
        Returns:
            Dictionary with detections, timings, and metadata
        """
        import pyzed.sl as sl
        import cv2
        import numpy as np
        
        timings = {}
        
        # Check if we've reached end of SVO
        if self.frame_index >= self.total_frames:
            return None  # Signal completion
        
        # 1. Grab frame
        grab_start = time.time()
        grab_status = self.camera.grab(self.runtime_params)
        
        if grab_status == sl.ERROR_CODE.END_OF_SVOFILE_REACHED:
            return None  # End of file
        
        if grab_status != sl.ERROR_CODE.SUCCESS:
            # Skip corrupted frames
            self.frame_index += 1
            return {'detections': [], 'timings': {}, 'skipped': True}
        
        self.camera.retrieve_image(self.image, sl.VIEW.LEFT)
        timings['grab'] = (time.time() - grab_start) * 1000
        
        # Convert to numpy for YOLO
        img_np = self.image.get_data()[:, :, :3]  # Remove alpha channel
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGBA2BGR)
        
        # 2. Run inference
        inference_start = time.time()
        results = self.model(img_bgr, conf=self.conf_threshold, verbose=False)
        timings['inference'] = (time.time() - inference_start) * 1000
        
        # 3. Extract depth ONLY in bbox areas
        depth_start = time.time()
        detections = []
        
        # Retrieve depth once for all boxes
        self.camera.retrieve_measure(self.depth, sl.MEASURE.DEPTH)
        depth_np = self.depth.get_data()
        
        for box in results[0].boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            
            # Extract bbox region from depth
            depth_roi = depth_np[y1:y2, x1:x2]
            
            # Calculate stats (ignoring invalid depth)
            # Valid depth range: 1.0m to 40.0m
            valid_depth = depth_roi[
                ~np.isnan(depth_roi) & 
                ~np.isinf(depth_roi) & 
                (depth_roi > 0) &
                (depth_roi >= 1.0) &  # 1 meter minimum
                (depth_roi <= 40.0)   # 40 meters maximum
            ]
            
            # Calculate mean depth (average all valid pixels in bbox)
            mean_depth = float(np.mean(valid_depth)) if len(valid_depth) > 0 else -1.0
            std_depth = float(np.std(valid_depth)) if len(valid_depth) > 0 else 0.0
            
            detections.append({
                'class': int(box.cls[0]),
                'confidence': float(box.conf[0]),
                'bbox': [x1, y1, x2, y2],
                'depth_mean': mean_depth,
                'depth_std': std_depth,
                'depth_valid_pixels': len(valid_depth)
            })
        
        timings['depth'] = (time.time() - depth_start) * 1000
        
        # 4. Save images or annotations
        if self.save_images and self.output_dir:
            save_start = time.time()
            
            # Draw YOLO annotations on image
            annotated_img = img_bgr.copy()
            
            for det in detections:
                x1, y1, x2, y2 = det['bbox']
                conf = det['confidence']
                depth = det['depth_mean']
                
                # Draw bbox
                color = (0, 255, 0) if det['class'] == 0 else (0, 0, 255)
                cv2.rectangle(annotated_img, (x1, y1), (x2, y2), color, 2)
                
                # Draw label with confidence and depth
                if depth > 0:
                    label = f"Conf:{conf:.2f} Depth:{depth:.2f}m"
                else:
                    label = f"Conf:{conf:.2f} No depth"
                
                # Label background
                label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(annotated_img, (x1, y1 - 20), (x1 + label_size[0], y1), color, -1)
                cv2.putText(annotated_img, label, (x1, y1 - 5), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Save annotated image only (skip raw for speed)
            frame_filename = f"frame_{self.frame_index:06d}.jpg"
            save_path = Path(self.output_dir) / frame_filename
            cv2.imwrite(str(save_path), annotated_img)
            
            timings['save'] = (time.time() - save_start) * 1000
        
        elif self.save_annotations_only and self.output_dir:
            # Fast mode: Save only YOLO .txt annotations
            save_start = time.time()
            
            # Get image dimensions for YOLO normalization
            img_height, img_width = img_bgr.shape[:2]
            
            # Create YOLO format annotations
            annotation_lines = []
            for det in detections:
                x1, y1, x2, y2 = det['bbox']
                class_id = det['class']
                
                # Convert to YOLO format (normalized center x, center y, width, height)
                center_x = ((x1 + x2) / 2) / img_width
                center_y = ((y1 + y2) / 2) / img_height
                width = (x2 - x1) / img_width
                height = (y2 - y1) / img_height
                
                # YOLO format: class_id center_x center_y width height
                annotation_lines.append(f"{class_id} {center_x:.6f} {center_y:.6f} {width:.6f} {height:.6f}")
            
            # Save annotation file
            annotation_filename = f"frame_{self.frame_index:06d}.txt"
            annotation_path = Path(self.output_dir) / annotation_filename
            
            if annotation_lines:  # Only save if there are detections
                with open(annotation_path, 'w') as f:
                    f.write('\n'.join(annotation_lines))
            else:
                # Create empty file to maintain frame index consistency
                annotation_path.touch()
            
            timings['save'] = (time.time() - save_start) * 1000
        
        # Send preview to GUI (always, regardless of save mode or detections)
        if self.preview_callback:
            # Create annotated image for preview (show frame even if no detections)
            preview_img = img_bgr.copy()
            
            # Draw detections if any
            if detections:
                for det in detections:
                    x1, y1, x2, y2 = det['bbox']
                    conf = det['confidence']
                    depth = det['depth_mean']
                    
                    # Draw bbox
                    color = (0, 255, 0) if det['class'] == 0 else (0, 0, 255)
                    cv2.rectangle(preview_img, (x1, y1), (x2, y2), color, 2)
                    
                    # Draw label with confidence and depth
                    if depth > 0:
                        label = f"Conf:{conf:.2f} Depth:{depth:.2f}m"
                    else:
                        label = f"Conf:{conf:.2f} No depth"
                    
                    # Label background
                    label_size, _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cv2.rectangle(preview_img, (x1, y1 - 20), (x1 + label_size[0], y1), color, -1)
                    cv2.putText(preview_img, label, (x1, y1 - 5), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Convert to RGB for Qt display
            preview_rgb = cv2.cvtColor(preview_img, cv2.COLOR_BGR2RGB)
            self.preview_callback(preview_rgb)
        
        self.frame_index += 1
        
        return {
            'detections': detections,
            'timings': timings,
            'frame_index': self.frame_index,
            'total_frames': self.total_frames,
            'depth_array': depth_np  # Include full depth map for visualizations
        }
    
    def cleanup(self):
        """Cleanup camera and model."""
        if self.camera:
            self.camera.close()
        self.camera = None
        self.model = None


class TrackingPipelineScenario(BenchmarkScenario):
    """
    Scenario 3: Full tracking pipeline with mathematical tracker.
    
    Pipeline:
    1. SVO grab + YOLO detection (or pre-loaded images)
    2. Tracker update (Kalman, SORT, etc.)
    3. Track management (association, creation, deletion)
    
    This will be the base for real-time tracking on the drone.
    """
    
    def __init__(self):
        super().__init__(
            "Tracking Pipeline",
            "YOLO + Mathematical Tracker (Kalman/SORT)"
        )
        self.model = None
        self.tracker = None
    
    def setup(self, config: Dict[str, Any]) -> bool:
        """Setup model and tracker."""
        # TODO: Implement when we add tracking algorithms
        # Will support: Kalman, SORT, DeepSORT, ByteTrack, etc.
        return False
    
    def run_frame(self, frame_data: Any) -> Dict[str, Any]:
        """Run detection + tracking."""
        # TODO: Implement
        return {'detections': [], 'timings': {}}
    
    def cleanup(self):
        """Cleanup resources."""
        pass


class ExternalPluginScenario(BenchmarkScenario):
    """
    Scenario 4: External algorithm plugin.
    
    Allows users to test their own algorithms by providing:
    - A Python module with process_frame() function
    - Input/output contracts for integration
    
    This enables testing custom tracking/detection pipelines
    before integrating into main codebase.
    """
    
    def __init__(self):
        super().__init__(
            "External Plugin",
            "User-provided algorithm plugin"
        )
        self.plugin_module = None
    
    def setup(self, config: Dict[str, Any]) -> bool:
        """Load external plugin."""
        # TODO: Implement dynamic module loading
        # plugin_path = config.get('plugin_path')
        # self.plugin_module = importlib.import_module(plugin_path)
        return False
    
    def run_frame(self, frame_data: Any) -> Dict[str, Any]:
        """Run external algorithm."""
        # TODO: Call plugin_module.process_frame(frame_data)
        return {'detections': [], 'timings': {}}
    
    def cleanup(self):
        """Cleanup plugin."""
        pass


# Registry of available scenarios
SCENARIO_REGISTRY = {
    'pure_inference': PureInferenceScenario,
    'svo_pipeline': SVOPipelineScenario,
    'tracking_pipeline': TrackingPipelineScenario,
    'external_plugin': ExternalPluginScenario
}


def get_scenario(scenario_type: str) -> Optional[BenchmarkScenario]:
    """Get scenario instance by type."""
    scenario_class = SCENARIO_REGISTRY.get(scenario_type)
    if scenario_class:
        return scenario_class()
    return None


def compare_scenarios(results: List[BenchmarkResult]) -> Dict[str, Any]:
    """
    Compare results from multiple scenarios.
    
    Returns:
        Dictionary with comparison metrics
    """
    comparison = {
        'scenarios': [],
        'fps_comparison': {},
        'component_breakdown': {},
        'recommendations': []
    }
    
    for result in results:
        comparison['scenarios'].append({
            'name': result.scenario_name,
            'fps': result.mean_fps,
            'latency_ms': result.mean_latency_ms,
            'components': result.component_times
        })
        
        comparison['fps_comparison'][result.scenario_name] = result.mean_fps
    
    # Find bottlenecks
    for result in results:
        if result.component_times:
            slowest = max(result.component_times.items(), key=lambda x: x[1])
            comparison['recommendations'].append(
                f"{result.scenario_name}: Bottleneck is '{slowest[0]}' ({slowest[1]:.2f}ms)"
            )
    
    return comparison
