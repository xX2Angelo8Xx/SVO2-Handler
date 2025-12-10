#!/usr/bin/env python3
"""
SVO2 Grab Speed Test
Quick script to measure raw grab performance from SVO2 files.
Tests: Left image, Right image, and Full depth map retrieval.

Usage:
    python scripts/svo2_grab_speed_test.py
    
    Enter SVO2 file path when prompted.
    Press CTRL+C to stop and show final statistics.
"""

import sys
import time
import signal
from pathlib import Path

try:
    import pyzed.sl as sl
    import numpy as np
except ImportError as e:
    print(f"ERROR: Missing dependency - {e}")
    print("Please install: pip install numpy")
    print("ZED SDK must be installed separately")
    sys.exit(1)


class SVO2GrabTester:
    """Test raw grab speed from SVO2 files or live camera."""
    
    def __init__(self, svo_path: str = None, use_live: bool = False):
        self.svo_path = Path(svo_path) if svo_path else None
        self.use_live = use_live
        self.camera = sl.Camera()
        self.running = True
        
        # Depth mode (set by main before initialize)
        self.depth_mode = sl.DEPTH_MODE.NONE
        self.depth_name = "NONE"
        
        # ROI settings (set by main before initialize)
        self.roi_percent = 100  # 100%, 50%, or 25%
        self.depth_roi = None  # Will be set after camera opens
        
        # Depth analysis settings (set by main before initialize)
        self.depth_hz = None  # Target Hz for depth computation (None = every frame)
        self.analyze_depth = False  # Whether to analyze and print depth statistics
        
        # Stats
        self.frame_count = 0
        self.depth_frame_count = 0  # Frames where depth was computed
        self.start_time = None
        self.total_frames = 0
        
        # Depth statistics
        self.last_depth_avg = 0.0
        self.last_depth_std = 0.0
        self.last_depth_min = 0.0
        self.last_depth_max = 0.0
        self.last_depth_time = None
        
        # Setup signal handler for CTRL+C
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, sig, frame):
        """Handle CTRL+C gracefully."""
        print("\n\n⏹️  Stopping test...")
        self.running = False
    
    def _analyze_depth(self, depth_map: sl.Mat):
        """Analyze depth data and update statistics."""
        # Get depth data as numpy array
        depth_data = depth_map.get_data()
        
        # Filter out invalid depth values (NaN, inf, <= 0)
        valid_mask = np.isfinite(depth_data) & (depth_data > 0)
        
        if np.any(valid_mask):
            valid_depths = depth_data[valid_mask]
            
            # Calculate statistics
            self.last_depth_avg = float(np.mean(valid_depths))
            self.last_depth_std = float(np.std(valid_depths))
            self.last_depth_min = float(np.min(valid_depths))
            self.last_depth_max = float(np.max(valid_depths))
            self.last_depth_time = time.time()
        else:
            # No valid depth data
            self.last_depth_avg = 0.0
            self.last_depth_std = 0.0
            self.last_depth_min = 0.0
            self.last_depth_max = 0.0
    
    def initialize(self) -> bool:
        """Initialize SVO2 file or live camera."""
        # Setup init parameters
        init_params = sl.InitParameters()
        init_params.depth_mode = self.depth_mode
        init_params.coordinate_units = sl.UNIT.METER
        
        if self.use_live:
            # Live camera mode
            print("📹 Opening LIVE camera feed...")
            init_params.camera_resolution = sl.RESOLUTION.HD720
            init_params.camera_fps = 60
        else:
            # SVO2 file mode
            if not self.svo_path.exists():
                print(f"❌ ERROR: SVO2 file not found: {self.svo_path}")
                return False
            
            print(f"📹 Opening SVO2 file: {self.svo_path.name}")
            init_params.set_from_svo_file(str(self.svo_path))
            init_params.svo_real_time_mode = False  # Process as fast as possible
        
        # Open camera
        source_name = "LIVE camera" if self.use_live else "SVO2 file"
        print(f"⏳ Initializing ZED from {source_name} ({self.depth_name} depth)...")
        if self.depth_mode in [sl.DEPTH_MODE.NEURAL, sl.DEPTH_MODE.NEURAL_PLUS]:
            print("   This may take 30-60 seconds for first-time initialization...")
        
        err = self.camera.open(init_params)
        if err != sl.ERROR_CODE.SUCCESS:
            print(f"❌ ERROR: Failed to open {source_name}: {err}")
            return False
        
        # Get camera info
        info = self.camera.get_camera_information()
        resolution = info.camera_configuration.resolution
        fps = info.camera_configuration.fps
        
        if self.use_live:
            print("✅ Live camera opened successfully!")
            print(f"   📊 Mode: LIVE STREAMING")
            self.total_frames = 999999  # Unlimited for live
        else:
            self.total_frames = self.camera.get_svo_number_of_frames()
            print("✅ SVO2 opened successfully!")
            print(f"   📊 Total frames: {self.total_frames}")
        
        print(f"   🎬 FPS: {fps}")
        print(f"   📐 Resolution: {resolution.width}x{resolution.height}")
        print(f"   🧠 Depth mode: {self.depth_name}")
        
        # Setup ROI for depth computation if not 100%
        if self.roi_percent < 100 and self.depth_mode != sl.DEPTH_MODE.NONE:
            width = resolution.width
            height = resolution.height
            
            # Calculate ROI size (centered)
            roi_width = int(width * self.roi_percent / 100)
            roi_height = int(height * self.roi_percent / 100)
            
            # Center the ROI
            x_start = (width - roi_width) // 2
            y_start = (height - roi_height) // 2
            
            # Create ROI structure
            self.depth_roi = sl.Rect()
            self.depth_roi.x = x_start
            self.depth_roi.y = y_start
            self.depth_roi.width = roi_width
            self.depth_roi.height = roi_height
            
            print(f"   🎯 Depth ROI: {self.roi_percent}% ({roi_width}x{roi_height}, centered)")
        else:
            print(f"   🎯 Depth ROI: Full frame (100%)")
        
        print()
        
        return True
    
    def run_test(self):
        """Run the grab speed test."""
        print("=" * 70)
        print("🚀 STARTING GRAB SPEED TEST")
        print("=" * 70)
        if self.depth_mode == sl.DEPTH_MODE.NONE:
            print("Testing: Left image + Right image (NO depth)")
        else:
            roi_desc = f" in {self.roi_percent}% ROI" if self.depth_roi else " (full frame)"
            hz_desc = f"every frame" if self.depth_hz is None else f"{self.depth_hz} Hz"
            print(f"Testing: Left + Right + Depth{roi_desc} ({self.depth_name}, {hz_desc})")
            if self.analyze_depth:
                print("Real-time depth analysis: ENABLED (avg, min, max, std)")
        print("Press CTRL+C to stop")
        print()
        
        # Create image containers
        left_image = sl.Mat()
        right_image = sl.Mat()
        depth_map = sl.Mat()
        
        self.start_time = time.time()
        last_update = self.start_time
        
        while self.running:
            # Grab frame
            grab_status = self.camera.grab()
            
            if grab_status == sl.ERROR_CODE.SUCCESS:
                # Retrieve left image
                self.camera.retrieve_image(left_image, sl.VIEW.LEFT)
                
                # Retrieve right image
                self.camera.retrieve_image(right_image, sl.VIEW.RIGHT)
                
                # Determine if we should compute depth this frame
                compute_depth = False
                if self.depth_mode != sl.DEPTH_MODE.NONE:
                    if self.depth_hz is None:
                        # Compute every frame
                        compute_depth = True
                    else:
                        # Compute every N-th frame based on target Hz
                        # Calculate frame interval: grab_fps / target_depth_hz
                        elapsed = time.time() - self.start_time
                        current_fps = self.frame_count / elapsed if elapsed > 0 else 60
                        frame_interval = max(1, int(current_fps / self.depth_hz))
                        compute_depth = (self.frame_count % frame_interval == 0)
                
                # Retrieve depth map (only if depth enabled and this is a depth frame)
                if compute_depth:
                    if self.depth_roi:
                        # Compute depth with reduced resolution (simulates smaller ROI)
                        roi_res = sl.Resolution(self.depth_roi.width, self.depth_roi.height)
                        self.camera.retrieve_measure(depth_map, sl.MEASURE.DEPTH, sl.MEM.CPU, roi_res)
                    else:
                        # Full frame depth
                        self.camera.retrieve_measure(depth_map, sl.MEASURE.DEPTH)
                    
                    self.depth_frame_count += 1
                    
                    # Analyze depth if requested
                    if self.analyze_depth:
                        self._analyze_depth(depth_map)
                
                self.frame_count += 1
                
                # Update stats every second
                current_time = time.time()
                if current_time - last_update >= 1.0:
                    elapsed = current_time - self.start_time
                    fps = self.frame_count / elapsed
                    percent = (self.frame_count / self.total_frames) * 100
                    
                    # Build status line
                    status = f"📊 Frame {self.frame_count}/{self.total_frames} ({percent:.1f}%) | FPS: {fps:.2f}"
                    
                    # Add depth stats if analyzing
                    if self.analyze_depth and self.depth_frame_count > 0:
                        depth_fps = self.depth_frame_count / elapsed
                        status += f" | Depth: {depth_fps:.1f} Hz"
                        
                        if self.last_depth_time and (current_time - self.last_depth_time) < 2.0:
                            status += f" | Avg: {self.last_depth_avg:.2f}m"
                            status += f" | Min: {self.last_depth_min:.2f}m"
                            status += f" | Max: {self.last_depth_max:.2f}m"
                            status += f" | Std: {self.last_depth_std:.2f}m"
                    
                    status += f" | Elapsed: {elapsed:.1f}s"
                    
                    # Clear line and print (pad to 120 chars to clear old text)
                    print(f"{status:<120}", end='\r')
                    
                    last_update = current_time
            
            elif grab_status == sl.ERROR_CODE.END_OF_SVOFILE_REACHED:
                print("\n\n📽️  Reached end of SVO2 file")
                self.running = False
            
            else:
                print(f"\n❌ ERROR during grab: {grab_status}")
                self.running = False
        
        # Final stats
        self._print_final_stats()
    
    def _print_final_stats(self):
        """Print final statistics."""
        elapsed = time.time() - self.start_time
        fps = self.frame_count / elapsed if elapsed > 0 else 0
        
        print("\n")
        print("=" * 70)
        print("📊 FINAL STATISTICS")
        print("=" * 70)
        print(f"Total frames processed: {self.frame_count}/{self.total_frames}")
        print(f"Total time: {elapsed:.2f}s")
        print(f"Average FPS (grab): {fps:.2f}")
        print(f"Average frame time: {(elapsed/self.frame_count*1000):.2f}ms" if self.frame_count > 0 else "N/A")
        
        # Depth statistics if enabled
        if self.depth_mode != sl.DEPTH_MODE.NONE and self.depth_frame_count > 0:
            depth_fps = self.depth_frame_count / elapsed
            skip_ratio = self.frame_count / self.depth_frame_count if self.depth_frame_count > 0 else 0
            print()
            print("Depth computation:")
            print(f"  • Depth frames: {self.depth_frame_count}/{self.frame_count}")
            print(f"  • Depth Hz: {depth_fps:.2f}")
            print(f"  • Frame skip: Every {skip_ratio:.1f} frames")
            if self.last_depth_time:
                print(f"  • Last avg depth: {self.last_depth_avg:.2f}m")
                print(f"  • Last depth range: {self.last_depth_min:.2f}m - {self.last_depth_max:.2f}m")
                print(f"  • Last std dev: {self.last_depth_std:.2f}m")
        
        print()
        print("Components retrieved:")
        print("  • Left image (HD720: 1280x720)")
        print("  • Right image (HD720: 1280x720)")
        if self.depth_mode != sl.DEPTH_MODE.NONE:
            roi_desc = f" at {self.roi_percent}% ROI" if self.roi_percent < 100 else ""
            print(f"  • Depth map ({self.depth_name}{roi_desc})")
        else:
            print("  • Depth map: DISABLED")
        print("=" * 70)
    
    def cleanup(self):
        """Clean up resources."""
        if self.camera:
            self.camera.close()
        print("✅ Cleanup complete")


def main():
    """Main entry point."""
    print("╔══════════════════════════════════════════════════════════════════════════════╗")
    print("║                                                                              ║")
    print("║                    🚀 SVO2 GRAB SPEED TEST 🚀                                ║")
    print("║                                                                              ║")
    print("╚══════════════════════════════════════════════════════════════════════════════╝")
    print()
    
    # Choose source: Live camera or SVO2 file
    print("📹 Select video source:")
    print("  1) SVO2 file (playback from disk)")
    print("  2) Live camera (real-time streaming)")
    
    source_choice = input("\nChoose source (1-2) [default: 1]: ").strip() or "1"
    
    use_live = (source_choice == '2')
    svo_path = None
    
    if use_live:
        print("\n✅ Selected: LIVE camera feed")
    else:
        # Get SVO2 path from user
        svo_path = input("\nEnter SVO2 file path: ").strip()
        
        if not svo_path:
            print("❌ No path provided. Exiting.")
            return
        
        print(f"\n✅ Selected: SVO2 file playback")
    
    # Choose depth mode
    print("\n📊 Select depth mode:")
    print("  1) NONE - No depth (fastest, ~60 FPS)")
    print("  2) PERFORMANCE - Fast depth (~30 FPS)")
    print("  3) QUALITY - Balanced depth (~15 FPS)")
    print("  4) ULTRA - Best quality (~10 FPS)")
    print("  5) NEURAL - AI depth (~8 FPS)")
    print("  6) NEURAL_PLUS - Best AI depth (~8-10 FPS, 30-60s init)")
    
    depth_choice = input("\nChoose depth mode (1-6) [default: 1]: ").strip() or "1"
    
    # Map choice to depth mode
    depth_modes = {
        '1': ('NONE', sl.DEPTH_MODE.NONE),
        '2': ('PERFORMANCE', sl.DEPTH_MODE.PERFORMANCE),
        '3': ('QUALITY', sl.DEPTH_MODE.QUALITY),
        '4': ('ULTRA', sl.DEPTH_MODE.ULTRA),
        '5': ('NEURAL', sl.DEPTH_MODE.NEURAL),
        '6': ('NEURAL_PLUS', sl.DEPTH_MODE.NEURAL_PLUS)
    }
    
    if depth_choice not in depth_modes:
        print(f"⚠️  Invalid choice '{depth_choice}', using NONE (fastest)")
        depth_choice = '1'
    
    depth_name, depth_mode = depth_modes[depth_choice]
    print(f"\n✅ Selected depth: {depth_name}")
    
    # Choose ROI size (only if depth is enabled)
    roi_percent = 100
    if depth_mode != sl.DEPTH_MODE.NONE:
        print("\n🎯 Select depth computation area (simulates YOLO detection):")
        print("  1) 100% - Full frame (1280x720)")
        print("  2)  50% - Half frame (640x360, centered)")
        print("  3)  25% - Quarter frame (320x180, centered)")
        
        roi_choice = input("\nChoose ROI size (1-3) [default: 1]: ").strip() or "1"
        
        roi_options = {
            '1': 100,
            '2': 50,
            '3': 25
        }
        
        if roi_choice not in roi_options:
            print("⚠️  Invalid choice, using 100% (full frame)")
            roi_percent = 100
        else:
            roi_percent = roi_options[roi_choice]
        
        print(f"\n✅ Selected ROI: {roi_percent}% of frame")
        
        # Choose depth analysis frequency
        print("\n⏱️  Select depth computation frequency:")
        print("  1) Every frame (max quality, lowest FPS)")
        print("  2) 10 Hz (recommended for tracking)")
        print("  3) 5 Hz (good for slow targets)")
        print("  4) 1 Hz (verification only)")
        print("  5) Custom Hz")
        
        hz_choice = input("\nChoose frequency (1-5) [default: 2]: ").strip() or "2"
        
        depth_hz = None
        if hz_choice == '1':
            depth_hz = None  # Every frame
            print("\n✅ Selected: Every frame (no skipping)")
        elif hz_choice == '2':
            depth_hz = 10
            print("\n✅ Selected: 10 Hz")
        elif hz_choice == '3':
            depth_hz = 5
            print("\n✅ Selected: 5 Hz")
        elif hz_choice == '4':
            depth_hz = 1
            print("\n✅ Selected: 1 Hz")
        elif hz_choice == '5':
            try:
                custom_hz = input("Enter custom Hz (1-60): ").strip()
                depth_hz = float(custom_hz)
                if depth_hz < 1 or depth_hz > 60:
                    print("⚠️  Invalid Hz, using 10 Hz")
                    depth_hz = 10
                else:
                    print(f"\n✅ Selected: {depth_hz} Hz")
            except ValueError:
                print("⚠️  Invalid input, using 10 Hz")
                depth_hz = 10
        else:
            print("⚠️  Invalid choice, using 10 Hz")
            depth_hz = 10
    else:
        depth_hz = None
    
    # Create tester
    tester = SVO2GrabTester(svo_path=svo_path, use_live=use_live)
    tester.depth_mode = depth_mode
    tester.depth_name = depth_name
    tester.roi_percent = roi_percent
    tester.depth_hz = depth_hz
    tester.analyze_depth = (depth_mode != sl.DEPTH_MODE.NONE)  # Enable analysis if depth is on
    
    try:
        # Initialize
        if not tester.initialize():
            return
        
        # Run test
        tester.run_test()
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Always cleanup
        tester.cleanup()
    
    print("\n👋 Done!")


if __name__ == "__main__":
    main()
