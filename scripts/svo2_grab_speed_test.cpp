/**
 * SVO2 Grab Speed Test - C++ Version
 * 
 * Measures raw grab performance from SVO2 files in C++.
 * Compare with Python version to see performance differences.
 * 
 * Compilation:
 *   g++ -o svo2_grab_test_cpp svo2_grab_speed_test.cpp \
 *       -I/usr/local/zed/include \
 *       -L/usr/local/zed/lib \
 *       -lsl_zed \
 *       -std=c++14 \
 *       -O3
 * 
 * Usage:
 *   ./svo2_grab_test_cpp
 */

#include <sl/Camera.hpp>
#include <iostream>
#include <chrono>
#include <iomanip>
#include <csignal>
#include <string>
#include <thread>

using namespace sl;
using namespace std;

// Global flag for CTRL+C handling
volatile sig_atomic_t running = 1;

void signal_handler(int signal) {
    cout << "\n\n⏹️  Stopping test..." << endl;
    running = 0;
}

class SVO2GrabTester {
private:
    Camera camera;
    string svo_path;
    bool use_live;
    DEPTH_MODE depth_mode;
    string depth_name;
    int roi_percent;
    Rect depth_roi;
    bool use_roi;
    
    int frame_count = 0;
    int total_frames = 0;
    chrono::high_resolution_clock::time_point start_time;
    
public:
    SVO2GrabTester(const string& path, bool live, DEPTH_MODE mode, const string& mode_name, int roi) 
        : svo_path(path), use_live(live), depth_mode(mode), depth_name(mode_name), 
          roi_percent(roi), use_roi(false) {}
    
    bool initialize() {
        // Setup init parameters
        InitParameters init_params;
        init_params.depth_mode = depth_mode;
        init_params.coordinate_units = UNIT::METER;
        
        if (use_live) {
            // Live camera mode
            cout << "📹 Opening LIVE camera feed..." << endl;
            init_params.camera_resolution = RESOLUTION::HD720;
            init_params.camera_fps = 60;
        } else {
            // SVO2 file mode
            cout << "📹 Opening SVO2 file: " << svo_path << endl;
            init_params.input.setFromSVOFile(svo_path.c_str());
            init_params.svo_real_time_mode = false;  // Process as fast as possible
        }
        
        // Open camera
        string source_name = use_live ? "LIVE camera" : "SVO2 file";
        cout << "⏳ Initializing ZED from " << source_name << " (" << depth_name << " depth)..." << endl;
        if (depth_mode == DEPTH_MODE::NEURAL || depth_mode == DEPTH_MODE::NEURAL_PLUS) {
            cout << "   This may take 30-60 seconds for first-time initialization..." << endl;
        }
        
        ERROR_CODE err = camera.open(init_params);
        if (err != ERROR_CODE::SUCCESS) {
            cout << "❌ ERROR: Failed to open " << source_name << ": " << err << endl;
            return false;
        }
        
        // Get camera info
        CameraInformation cam_info = camera.getCameraInformation();
        Resolution resolution = cam_info.camera_configuration.resolution;
        float fps = cam_info.camera_configuration.fps;
        
        if (use_live) {
            cout << "✅ Live camera opened successfully!" << endl;
            cout << "   📊 Mode: LIVE STREAMING" << endl;
            total_frames = 999999;  // Unlimited for live
        } else {
            total_frames = camera.getSVONumberOfFrames();
            cout << "✅ SVO2 opened successfully!" << endl;
            cout << "   📊 Total frames: " << total_frames << endl;
        }
        
        cout << "   🎬 FPS: " << fps << endl;
        cout << "   📐 Resolution: " << resolution.width << "x" << resolution.height << endl;
        cout << "   🧠 Depth mode: " << depth_name << endl;
        
        // Setup ROI for depth computation if not 100%
        if (roi_percent < 100 && depth_mode != DEPTH_MODE::NONE) {
            int width = resolution.width;
            int height = resolution.height;
            
            // Calculate ROI size (centered)
            int roi_width = (width * roi_percent) / 100;
            int roi_height = (height * roi_percent) / 100;
            
            // Center the ROI
            int x_start = (width - roi_width) / 2;
            int y_start = (height - roi_height) / 2;
            
            // Create ROI structure
            depth_roi.x = x_start;
            depth_roi.y = y_start;
            depth_roi.width = roi_width;
            depth_roi.height = roi_height;
            use_roi = true;
            
            cout << "   🎯 Depth ROI: " << roi_percent << "% (" << roi_width << "x" 
                 << roi_height << ", centered)" << endl;
        } else {
            cout << "   🎯 Depth ROI: Full frame (100%)" << endl;
        }
        
        cout << endl;
        
        return true;
    }
    
    void run_test() {
        cout << "======================================================================" << endl;
        cout << "🚀 STARTING GRAB SPEED TEST (C++)" << endl;
        cout << "======================================================================" << endl;
        
        if (depth_mode == DEPTH_MODE::NONE) {
            cout << "Testing: Left image + Right image (NO depth)" << endl;
        } else {
            string roi_desc = use_roi ? " in " + to_string(roi_percent) + "% ROI" : " (full frame)";
            cout << "Testing: Left image + Right image + Depth map" << roi_desc 
                 << " (" << depth_name << ")" << endl;
        }
        cout << "Press CTRL+C to stop" << endl;
        cout << endl;
        
        // Create image containers
        Mat left_image, right_image, depth_map;
        
        start_time = chrono::high_resolution_clock::now();
        auto last_update = start_time;
        
        while (running) {
            // Grab frame
            ERROR_CODE grab_status = camera.grab();
            
            if (grab_status == ERROR_CODE::SUCCESS) {
                // Retrieve left image
                camera.retrieveImage(left_image, VIEW::LEFT);
                
                // Retrieve right image
                camera.retrieveImage(right_image, VIEW::RIGHT);
                
                // Retrieve depth map (only if depth enabled)
                if (depth_mode != DEPTH_MODE::NONE) {
                    if (use_roi) {
                        // Compute depth with reduced resolution (simulates smaller ROI)
                        Resolution roi_res(depth_roi.width, depth_roi.height);
                        camera.retrieveMeasure(depth_map, MEASURE::DEPTH, MEM::CPU, roi_res);
                    } else {
                        // Full frame depth
                        camera.retrieveMeasure(depth_map, MEASURE::DEPTH);
                    }
                }
                
                frame_count++;
                
                // Update stats every second
                auto current_time = chrono::high_resolution_clock::now();
                auto elapsed_since_update = chrono::duration_cast<chrono::milliseconds>(
                    current_time - last_update).count();
                
                if (elapsed_since_update >= 1000) {
                    auto elapsed = chrono::duration_cast<chrono::milliseconds>(
                        current_time - start_time).count() / 1000.0;
                    double fps = frame_count / elapsed;
                    double percent = (static_cast<double>(frame_count) / total_frames) * 100.0;
                    
                    cout << "\r📊 Frame " << frame_count << "/" << total_frames 
                         << " (" << fixed << setprecision(1) << percent << "%) | "
                         << "FPS: " << setprecision(2) << fps << " | "
                         << "Elapsed: " << setprecision(1) << elapsed << "s" << flush;
                    
                    last_update = current_time;
                }
            }
            else if (grab_status == ERROR_CODE::END_OF_SVOFILE_REACHED) {
                cout << "\n\n📽️  Reached end of SVO2 file" << endl;
                running = 0;
            }
            else {
                cout << "\n❌ ERROR during grab: " << grab_status << endl;
                running = 0;
            }
        }
        
        print_final_stats();
    }
    
    void print_final_stats() {
        auto end_time = chrono::high_resolution_clock::now();
        auto elapsed = chrono::duration_cast<chrono::milliseconds>(
            end_time - start_time).count() / 1000.0;
        double fps = (elapsed > 0) ? frame_count / elapsed : 0;
        double frame_time = (frame_count > 0) ? (elapsed / frame_count) * 1000.0 : 0;
        
        cout << "\n" << endl;
        cout << "======================================================================" << endl;
        cout << "📊 FINAL STATISTICS (C++)" << endl;
        cout << "======================================================================" << endl;
        cout << "Total frames processed: " << frame_count << "/" << total_frames << endl;
        cout << "Total time: " << fixed << setprecision(2) << elapsed << "s" << endl;
        cout << "Average FPS: " << setprecision(2) << fps << endl;
        cout << "Average frame time: " << setprecision(2) << frame_time << "ms" << endl;
        cout << endl;
        cout << "Components retrieved per frame:" << endl;
        cout << "  • Left image (HD720: 1280x720)" << endl;
        cout << "  • Right image (HD720: 1280x720)" << endl;
        if (depth_mode != DEPTH_MODE::NONE) {
            cout << "  • Depth map (HD720: 1280x720, float32, " << depth_name << ")" << endl;
        } else {
            cout << "  • Depth map: DISABLED (for maximum speed)" << endl;
        }
        cout << "======================================================================" << endl;
    }
    
    void cleanup() {
        camera.close();
        cout << "✅ Cleanup complete" << endl;
    }
};

int main() {
    cout << "╔══════════════════════════════════════════════════════════════════════════════╗" << endl;
    cout << "║                                                                              ║" << endl;
    cout << "║                  🚀 SVO2 GRAB SPEED TEST (C++) 🚀                            ║" << endl;
    cout << "║                                                                              ║" << endl;
    cout << "╚══════════════════════════════════════════════════════════════════════════════╝" << endl;
    cout << endl;
    
    // Setup signal handler
    signal(SIGINT, signal_handler);
    
    // Choose source: Live camera or SVO2 file
    cout << "📹 Select video source:" << endl;
    cout << "  1) SVO2 file (playback from disk)" << endl;
    cout << "  2) Live camera (real-time streaming)" << endl;
    
    cout << "\nChoose source (1-2) [default: 1]: ";
    string source_choice;
    getline(cin, source_choice);
    if (source_choice.empty()) source_choice = "1";
    
    bool use_live = (source_choice == "2");
    string svo_path;
    
    if (use_live) {
        cout << "\n✅ Selected: LIVE camera feed" << endl;
    } else {
        // Get SVO2 path from user
        cout << "\nEnter SVO2 file path: ";
        getline(cin, svo_path);
        
        if (svo_path.empty()) {
            cout << "❌ No path provided. Exiting." << endl;
            return 1;
        }
        
        cout << "\n✅ Selected: SVO2 file playback" << endl;
    }
    
    // Choose depth mode
    cout << "\n📊 Select depth mode:" << endl;
    cout << "  1) NONE - No depth (fastest, ~60 FPS)" << endl;
    cout << "  2) PERFORMANCE - Fast depth (~30 FPS)" << endl;
    cout << "  3) QUALITY - Balanced depth (~15 FPS)" << endl;
    cout << "  4) ULTRA - Best quality (~10 FPS)" << endl;
    cout << "  5) NEURAL - AI depth (~8 FPS)" << endl;
    cout << "  6) NEURAL_PLUS - Best AI depth (~8-10 FPS, 30-60s init)" << endl;
    
    cout << "\nChoose depth mode (1-6) [default: 1]: ";
    string depth_choice;
    getline(cin, depth_choice);
    if (depth_choice.empty()) depth_choice = "1";
    
    // Map choice to depth mode
    DEPTH_MODE depth_mode = DEPTH_MODE::NONE;
    string depth_name = "NONE";
    
    switch (depth_choice[0]) {
        case '1': depth_mode = DEPTH_MODE::NONE; depth_name = "NONE"; break;
        case '2': depth_mode = DEPTH_MODE::PERFORMANCE; depth_name = "PERFORMANCE"; break;
        case '3': depth_mode = DEPTH_MODE::QUALITY; depth_name = "QUALITY"; break;
        case '4': depth_mode = DEPTH_MODE::ULTRA; depth_name = "ULTRA"; break;
        case '5': depth_mode = DEPTH_MODE::NEURAL; depth_name = "NEURAL"; break;
        case '6': depth_mode = DEPTH_MODE::NEURAL_PLUS; depth_name = "NEURAL_PLUS"; break;
        default:
            cout << "⚠️  Invalid choice, using NONE (fastest)" << endl;
            depth_mode = DEPTH_MODE::NONE;
            depth_name = "NONE";
    }
    
    cout << "\n✅ Selected depth: " << depth_name << endl;
    
    // Choose ROI size (only if depth is enabled)
    int roi_percent = 100;
    if (depth_mode != DEPTH_MODE::NONE) {
        cout << "\n🎯 Select depth computation area (simulates YOLO detection):" << endl;
        cout << "  1) 100% - Full frame (1280x720)" << endl;
        cout << "  2)  50% - Half frame (640x360, centered)" << endl;
        cout << "  3)  25% - Quarter frame (320x180, centered)" << endl;
        
        cout << "\nChoose ROI size (1-3) [default: 1]: ";
        string roi_choice;
        getline(cin, roi_choice);
        if (roi_choice.empty()) roi_choice = "1";
        
        switch (roi_choice[0]) {
            case '1': roi_percent = 100; break;
            case '2': roi_percent = 50; break;
            case '3': roi_percent = 25; break;
            default:
                cout << "⚠️  Invalid choice, using 100% (full frame)" << endl;
                roi_percent = 100;
        }
        
        cout << "\n✅ Selected ROI: " << roi_percent << "% of frame" << endl;
    }
    
    // Create and run tester
    SVO2GrabTester tester(svo_path, use_live, depth_mode, depth_name, roi_percent);
    
    try {
        if (!tester.initialize()) {
            return 1;
        }
        
        tester.run_test();
    }
    catch (const exception& e) {
        cout << "\n\n❌ ERROR: " << e.what() << endl;
        tester.cleanup();
        return 1;
    }
    
    tester.cleanup();
    cout << "\n👋 Done!" << endl;
    
    return 0;
}
