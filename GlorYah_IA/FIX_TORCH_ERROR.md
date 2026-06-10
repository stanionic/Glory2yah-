# Fix: "No module named 'torch'" Error

## 🎯 Problem

You're getting: `ModuleNotFoundError: No module named 'torch'`

This happens because the AI modules (text and image generators) require PyTorch, which is a large AI library.

## ✅ Solutions (Choose One)

### Solution 1: Quick Start (No AI) - RECOMMENDED

Run the app **without** AI features. Video generation still works!

```bash
# 1. Install basic dependencies only (NO torch)
pip install -r requirements-basic.txt

# 2. Use smart startup script
python start.py
```

✅ **This works immediately!**
- Video generation: ✅ Works (uses OpenCV, no torch needed)
- Basic API: ✅ Works
- Text/Image/Code: ⚠️ Uses fallback responses

---

### Solution 2: Install PyTorch (Full AI)

Install all AI dependencies including PyTorch.

#### For CPU (no NVIDIA GPU):
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

#### For NVIDIA GPU (CUDA):
```bash
# Check CUDA version first
nvidia-smi

# For CUDA 11.8
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# For CUDA 12.1
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Then install rest
pip install -r requirements.txt
```

⏱️ **Download time:** 5-10 minutes  
💾 **Space needed:** ~5GB

---

### Solution 3: Minimal Mode (Partial Features)

Install only minimal dependencies:

```bash
pip install -r requirements-minimal.txt
python start.py
```

This includes:
- ✅ Flask backend
- ✅ Video generation (OpenCV)
- ⚠️ No text/image AI (uses fallback)

---

## 🚀 Recommended Quick Start

### Option A: Just Test the Backend (30 seconds)

```bash
# Install basic deps only
pip install Flask Flask-SQLAlchemy Flask-CORS Pillow numpy opencv-python

# Start
python start.py
```

### Option B: Full Installation with AI (10 minutes)

```bash
# Install PyTorch (CPU version)
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Install everything else
pip install -r requirements.txt

# Start
python start.py
```

---

## 📋 What Each Requirements File Does

| File | Size | Install Time | Features |
|------|------|--------------|----------|
| `requirements-basic.txt` | ~50MB | 30 sec | Backend + Video only |
| `requirements-minimal.txt` | ~100MB | 1 min | + Image processing |
| `requirements.txt` | ~5GB | 10 min | Full AI features |

---

## 🔍 Verify Your Installation

After installation, run:

```bash
python start.py
```

You should see:

**With basic deps:**
```
✓ flask
✓ flask_sqlalchemy
✓ flask_cors
✓ PIL (video)
✓ cv2 (video)
✓ numpy (video)
⚠ torch (AI) - not available
⚠ transformers (AI) - not available

🎬 Starting in VIDEO MODE
   Available: Video generation, basic responses
```

**With full deps:**
```
✓ flask
✓ flask_sqlalchemy
✓ flask_cors
✓ PIL (video)
✓ cv2 (video)
✓ numpy (video)
✓ torch (AI)
✓ transformers (AI)
✓ diffusers (AI)

🚀 Starting in FULL MODE
   All features available
```

---

## 🛠️ Smart Startup Script

The `start.py` script automatically:
- ✅ Detects what's installed
- ✅ Chooses the best mode
- ✅ Shows what's available
- ✅ Gives installation hints

Just run: `python start.py`

---

## 🐛 Troubleshooting

### Error: "Could not find a version that satisfies the requirement torch"

**Solution:** Specify the PyTorch index URL:
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

### Error: "No space left on device"

**Solution:** PyTorch is large. Free up ~5GB or use basic mode:
```bash
pip install -r requirements-basic.txt
```

### Error: Still getting import errors

**Solution:** Use the smart startup:
```bash
python start.py
# It will tell you exactly what's missing
```

---

## 📊 Feature Comparison

### Basic Mode (requirements-basic.txt)
- ✅ Flask API works
- ✅ Video generation (4 animation types)
- ✅ Database
- ✅ Admin panel
- ⚠️ Text generation: fallback responses
- ⚠️ Image generation: placeholder images
- ⚠️ Code generation: templates only

### Full Mode (requirements.txt)
- ✅ Everything in Basic mode
- ✅ AI text generation (Phi-2)
- ✅ AI image generation (Stable Diffusion)
- ✅ AI code generation
- ✅ Smart responses

---

## 💡 Recommendation

**For Development/Testing:**
```bash
pip install -r requirements-basic.txt
python start.py
```
Fast, works immediately, perfect for frontend development.

**For Production/Demo:**
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
python start.py
```
Full AI features, but requires time and space.

---

## ✅ Summary

**The torch error is now FIXED!**

The app now works in **3 modes**:

1. **FULL MODE** - All AI features (requires torch)
2. **VIDEO MODE** - Video gen only (no torch needed) ⭐ RECOMMENDED FOR TESTING
3. **FALLBACK MODE** - Basic API only

Choose your mode by installing the appropriate requirements file, then:

```bash
python start.py
```

The smart startup will detect what's available and start in the best mode!

---

## 🎯 Quick Commands

```bash
# Test immediately (no AI)
pip install -r requirements-basic.txt && python start.py

# Full installation (with AI)
pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install -r requirements.txt && python start.py

# Check what's available
python start.py
```

**Problem solved! The app now works with or without torch!** 🎉
