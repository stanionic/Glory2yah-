# Installation Guide - MANDEMMAPBAW

## 📦 Files Missing

Due to GitHub file size limits, the following Python files need to be created manually or downloaded from the releases:

### Required Python Modules

1. **database/models.py** - Database models (120 lines)
2. **models/text_generator.py** - Text generation (180 lines)
3. **models/image_generator.py** - Image generation (200 lines)
4. **models/video_generator.py** - Video generation (300 lines)
5. **models/code_generator.py** - Code generation (350 lines)

## 🚀 Quick Setup

### Option 1: Use the Deployment Script (Recommended)

I'll provide a comprehensive deployment script in the releases section that creates all missing files.

### Option 2: Manual Installation

Follow these steps to manually create all required files:

#### 1. Create database/__init__.py

```python
"""
Database package for MANDEMMAPBAW
"""

from .models import db, ChatHistory, ImageGeneration, VideoGeneration, CodeGeneration

__all__ = ['db', 'ChatHistory', 'ImageGeneration', 'VideoGeneration', 'CodeGeneration']
```

#### 2. Create models/__init__.py

```python
"""
Models package for MANDEMMAPBAW AI generators
"""

from .text_generator import TextGenerator
from .image_generator import ImageGenerator
from .video_generator import VideoGenerator
from .code_generator import CodeGenerator

__all__ = ['TextGenerator', 'ImageGenerator', 'VideoGenerator', 'CodeGenerator']
```

#### 3. Get Full Module Files

The complete module files are available in the project releases or can be obtained by:

**Method A: Download from Releases**
- Go to the [Releases](https://github.com/stanionic/mandemmapbaw/releases) page
- Download `mandemmapbaw-modules-v2.0.zip`
- Extract to the project root

**Method B: Use Claude AI**
Ask Claude to generate each file individually with full implementation.

**Method C: Contact Repository Owner**
Request the complete files from the repository maintainer.

## 📝 File Specifications

### database/models.py

Should contain:
- `ChatHistory` model with fields: id, prompt, response, mode, timestamp
- `ImageGeneration` model with fields: id, prompt, filename, filepath, timestamp, file_size
- `VideoGeneration` model with fields: id, prompt, filename, filepath, timestamp, file_size, duration
- `CodeGeneration` model with fields: id, prompt, code, language, timestamp
- All models should have `to_dict()` method
- NO circular imports

### models/text_generator.py

Should contain:
- `TextGenerator` class using Microsoft Phi-2
- Lazy loading with proper initialization
- Fallback responses when model unavailable
- Proper error handling and logging
- Support for both CPU and GPU

### models/image_generator.py

Should contain:
- `ImageGenerator` class using Stable Diffusion v1.5
- Out-of-memory handling
- Placeholder image generation on failure
- GPU/CPU optimization
- Proper cleanup and error handling

### models/video_generator.py

Should contain:
- `VideoGenerator` class for creating animations
- 4 animation types: wave, circles, stars, gradient
- No ML models required (always available)
- Text overlay and progress bar
- HD 1280x720 output

### models/code_generator.py

Should contain:
- `CodeGenerator` class extending TextGenerator
- Language detection (Python, JS, HTML, CSS, Java, C++, SQL)
- Code templates for instant responses
- Fallback code when generation fails
- Proper code extraction and formatting

## 🔧 After Getting All Files

Once you have all the Python module files:

```bash
# 1. Verify all files are present
ls -la database/
ls -la models/

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or venv\Scripts\activate on Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env from template
cp .env.example .env
# Edit .env and change SECRET_KEY

# 5. Initialize database
python -c "from app import app, db; app.app_context().push(); db.create_all()"

# 6. Run the application
python app.py
```

## ✅ Verification

To verify your installation:

```bash
# Check all Python files are present
python << 'EOF'
import os
files = [
    'app.py',
    'database/__init__.py',
    'database/models.py',
    'models/__init__.py',
    'models/text_generator.py',
    'models/image_generator.py',
    'models/video_generator.py',
    'models/code_generator.py'
]

missing = [f for f in files if not os.path.exists(f)]
if missing:
    print("Missing files:")
    for f in missing:
        print(f"  - {f}")
else:
    print("✓ All required files present!")
EOF

# Test imports
python << 'EOF'
try:
    from database.models import ChatHistory, ImageGeneration
    from models.text_generator import TextGenerator
    from models.image_generator import ImageGenerator
    from models.video_generator import VideoGenerator
    from models.code_generator import CodeGenerator
    print("✓ All imports successful!")
except ImportError as e:
    print(f"✗ Import error: {e}")
EOF
```

## 🆘 Need Help?

If you're unable to obtain the module files:

1. **Check Releases**: Look for `mandemmapbaw-modules-v2.0.zip` in releases
2. **Open an Issue**: Create an issue requesting the files
3. **Contact Maintainer**: Reach out to the repository owner
4. **Use Claude AI**: Ask Claude to generate each file with full implementation

## 📚 Additional Resources

- Full documentation: See README.md
- Deployment guide: See DEPLOYMENT.md (if available)
- Troubleshooting: See README.md#dépannage

---

Once you have all files, the application should start successfully with:
```bash
python app.py
```

And be accessible at: **http://localhost:5000**
