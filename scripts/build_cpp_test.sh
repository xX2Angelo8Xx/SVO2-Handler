#!/bin/bash
# Build script for C++ SVO2 grab speed test

echo "🔨 Compiling C++ SVO2 Grab Speed Test..."
echo ""

# Compiler settings
CXX=g++
TARGET=svo2_grab_test_cpp
SOURCE=svo2_grab_speed_test.cpp

# ZED SDK paths
ZED_INCLUDE=/usr/local/zed/include
ZED_LIB=/usr/local/zed/lib

# CUDA paths (for Jetson)
CUDA_INCLUDE=/usr/local/cuda-12.6/targets/aarch64-linux/include
CUDA_LIB=/usr/local/cuda-12.6/targets/aarch64-linux/lib

# Compile with optimizations
$CXX -o $TARGET $SOURCE \
    -I$ZED_INCLUDE \
    -I$CUDA_INCLUDE \
    -L$ZED_LIB \
    -L$CUDA_LIB \
    -lsl_zed \
    -lcudart \
    -std=c++14 \
    -O3 \
    -pthread

if [ $? -eq 0 ]; then
    echo "✅ Compilation successful!"
    echo ""
    echo "📦 Binary created: ./$TARGET"
    echo ""
    echo "Usage:"
    echo "  ./$TARGET"
    echo ""
else
    echo "❌ Compilation failed!"
    exit 1
fi
