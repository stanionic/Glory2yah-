# MANDEMMAPBAW - Training System Implementation

## 🎓 New Feature: User Training System

Allow users to upload examples to improve the AI:
- 📁 Upload images with descriptions
- 🎬 Upload videos with labels
- 💬 Submit chat conversations
- 💻 Share code examples

## 🏗️ Architecture

### Database Models

```python
# New tables for training data
class TrainingImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=False)
    tags = db.Column(db.String(500))
    user_id = db.Column(db.String(100))
    approved = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    file_size = db.Column(db.Integer)

class TrainingVideo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    description = db.Column(db.Text, nullable=False)
    tags = db.Column(db.String(500))
    user_id = db.Column(db.String(100))
    approved = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    duration = db.Column(db.Float)

class TrainingConversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_message = db.Column(db.Text, nullable=False)
    expected_response = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100))
    language = db.Column(db.String(20), default='kreyol')
    user_id = db.Column(db.String(100))
    approved = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    used_count = db.Column(db.Integer, default=0)

class TrainingCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prompt = db.Column(db.Text, nullable=False)
    code = db.Column(db.Text, nullable=False)
    language = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text)
    user_id = db.Column(db.String(100))
    approved = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    used_count = db.Column(db.Integer, default=0)
```

### File Upload Routes

```python
@app.route('/training/upload-image', methods=['POST'])
def upload_training_image():
    """Upload image example for training"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': 'No image file'}), 400
        
        file = request.files['image']
        description = request.form.get('description', '')
        tags = request.form.get('tags', '')
        
        if not description:
            return jsonify({'error': 'Description required'}), 400
        
        # Save file
        filename = secure_filename(file.filename)
        unique_filename = f"train_{uuid.uuid4().hex}_{filename}"
        filepath = Path('static/training/images') / unique_filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        file.save(str(filepath))
        
        # Save to database
        training_img = TrainingImage(
            filename=unique_filename,
            filepath=str(filepath),
            description=description,
            tags=tags,
            file_size=filepath.stat().st_size
        )
        db.session.add(training_img)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Image uploaded for training',
            'id': training_img.id
        })
    except Exception as e:
        logger.error(f"Training image upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/training/upload-video', methods=['POST'])
def upload_training_video():
    """Upload video example for training"""
    # Similar implementation for videos
    pass

@app.route('/training/submit-conversation', methods=['POST'])
def submit_training_conversation():
    """Submit conversation example"""
    try:
        data = request.get_json()
        
        user_message = data.get('user_message', '').strip()
        expected_response = data.get('expected_response', '').strip()
        category = data.get('category', 'general')
        language = data.get('language', 'kreyol')
        
        if not user_message or not expected_response:
            return jsonify({'error': 'Both message and response required'}), 400
        
        # Save to database
        training_conv = TrainingConversation(
            user_message=user_message,
            expected_response=expected_response,
            category=category,
            language=language
        )
        db.session.add(training_conv)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Conversation example saved',
            'id': training_conv.id
        })
    except Exception as e:
        logger.error(f"Training conversation error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/training/submit-code', methods=['POST'])
def submit_training_code():
    """Submit code example for training"""
    try:
        data = request.get_json()
        
        prompt = data.get('prompt', '').strip()
        code = data.get('code', '').strip()
        language = data.get('language', 'python')
        description = data.get('description', '')
        
        if not prompt or not code:
            return jsonify({'error': 'Prompt and code required'}), 400
        
        # Save to database
        training_code = TrainingCode(
            prompt=prompt,
            code=code,
            language=language,
            description=description
        )
        db.session.add(training_code)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Code example saved',
            'id': training_code.id
        })
    except Exception as e:
        logger.error(f"Training code error: {e}")
        return jsonify({'error': str(e)}), 500
```

### Enhanced Smart Fallback with User Training

```python
class SmartFallback:
    def __init__(self):
        self.patterns = self._load_patterns()
        self.context = []
        self.user_training = []  # NEW: User-submitted examples
        
    def load_user_training(self):
        """Load approved training examples from database"""
        try:
            # Get approved conversations
            conversations = TrainingConversation.query.filter_by(
                approved=True
            ).all()
            
            self.user_training = [
                {
                    'user_message': conv.user_message.lower(),
                    'response': conv.expected_response,
                    'category': conv.category
                }
                for conv in conversations
            ]
            
            logger.info(f"Loaded {len(self.user_training)} user training examples")
        except Exception as e:
            logger.error(f"Error loading user training: {e}")
    
    def generate(self, prompt, max_length=300):
        """Generate response with user training priority"""
        prompt_lower = prompt.lower().strip()
        
        # 1. Check user training examples first (highest priority)
        for example in self.user_training:
            similarity = self._calculate_similarity(
                prompt_lower, 
                example['user_message']
            )
            if similarity > 0.8:  # 80% match
                # Increment usage count
                self._increment_training_usage(example)
                return example['response']
        
        # 2. Fall back to pattern matching
        return self._pattern_matching_response(prompt)
    
    def _calculate_similarity(self, text1, text2):
        """Calculate text similarity (simple version)"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
```

### Training Interface Routes

```python
@app.route('/training')
def training_page():
    """Training interface page"""
    return render_template('training.html')

@app.route('/training/stats')
def training_stats():
    """Get training statistics"""
    try:
        stats = {
            'total_images': TrainingImage.query.count(),
            'total_videos': TrainingVideo.query.count(),
            'total_conversations': TrainingConversation.query.count(),
            'total_code': TrainingCode.query.count(),
            'approved_conversations': TrainingConversation.query.filter_by(
                approved=True
            ).count(),
            'pending_approval': (
                TrainingImage.query.filter_by(approved=False).count() +
                TrainingVideo.query.filter_by(approved=False).count() +
                TrainingConversation.query.filter_by(approved=False).count() +
                TrainingCode.query.filter_by(approved=False).count()
            )
        }
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/training/approve/<type>/<int:id>', methods=['POST'])
def approve_training(type, id):
    """Approve training data (admin only)"""
    try:
        model_map = {
            'image': TrainingImage,
            'video': TrainingVideo,
            'conversation': TrainingConversation,
            'code': TrainingCode
        }
        
        if type not in model_map:
            return jsonify({'error': 'Invalid type'}), 400
        
        item = model_map[type].query.get(id)
        if not item:
            return jsonify({'error': 'Not found'}), 404
        
        item.approved = True
        db.session.commit()
        
        # Reload user training if conversation
        if type == 'conversation':
            from models.smart_fallback import get_smart_fallback
            fallback = get_smart_fallback()
            fallback.load_user_training()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

## 🎨 Frontend - Training Interface

```html
<!-- templates/training.html -->
<!DOCTYPE html>
<html lang="ht">
<head>
    <meta charset="UTF-8">
    <title>MANDEMMAPBAW - Training</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <style>
        .training-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .training-section {
            background: white;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        
        .upload-area {
            border: 2px dashed #3498db;
            border-radius: 10px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s;
        }
        
        .upload-area:hover {
            background: #ecf0f1;
            border-color: #2980b9;
        }
        
        .upload-area.dragging {
            background: #d4e6f1;
            border-color: #2980b9;
        }
        
        .form-group {
            margin: 15px 0;
        }
        
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #2c3e50;
        }
        
        .form-group input,
        .form-group textarea,
        .form-group select {
            width: 100%;
            padding: 10px;
            border: 1px solid #bdc3c7;
            border-radius: 5px;
            font-size: 14px;
        }
        
        .form-group textarea {
            min-height: 100px;
            resize: vertical;
        }
        
        .submit-btn {
            background: #27ae60;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            transition: all 0.3s;
        }
        
        .submit-btn:hover {
            background: #229954;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 10px;
            text-align: center;
        }
        
        .stat-number {
            font-size: 36px;
            font-weight: bold;
        }
        
        .stat-label {
            font-size: 14px;
            opacity: 0.9;
        }
        
        .success-message {
            background: #d4edda;
            color: #155724;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
            display: none;
        }
        
        .error-message {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 5px;
            margin: 10px 0;
            display: none;
        }
    </style>
</head>
<body>
    <div class="training-container">
        <h1>🎓 MANDEMMAPBAW Training System</h1>
        <p>Ede amelyore AI a! Soumèt egzanp pou antrene sistèm nan.</p>
        
        <!-- Statistics -->
        <div class="training-section">
            <h2>📊 Estatistik Training</h2>
            <div class="stats-grid" id="statsGrid">
                <!-- Stats loaded dynamically -->
            </div>
        </div>
        
        <!-- Upload Images -->
        <div class="training-section">
            <h2>📷 Upload Imaj Training</h2>
            <div class="upload-area" id="imageUploadArea">
                <p>🖼️ Klike oswa glise imaj la isit</p>
                <input type="file" id="imageFile" accept="image/*" style="display:none;">
            </div>
            <div class="form-group">
                <label>Deskripsyon Imaj:</label>
                <textarea id="imageDescription" placeholder="Dekri sa ki nan imaj la an Kreyòl..."></textarea>
            </div>
            <div class="form-group">
                <label>Tags (separe ak vigil):</label>
                <input type="text" id="imageTags" placeholder="natirèl, peyizaj, ayiti">
            </div>
            <button class="submit-btn" onclick="submitImage()">📤 Soumèt Imaj</button>
            <div class="success-message" id="imageSuccess"></div>
            <div class="error-message" id="imageError"></div>
        </div>
        
        <!-- Submit Conversations -->
        <div class="training-section">
            <h2>💬 Soumèt Konvèsasyon Training</h2>
            <div class="form-group">
                <label>Mesaj Itilizatè:</label>
                <textarea id="userMessage" placeholder="Egzanp: Kijan pou m kreye yon sit wèb?"></textarea>
            </div>
            <div class="form-group">
                <label>Repons Atandi:</label>
                <textarea id="expectedResponse" placeholder="Egzanp repons ki bon an Kreyòl..."></textarea>
            </div>
            <div class="form-group">
                <label>Kategori:</label>
                <select id="conversationCategory">
                    <option value="general">Jeneral</option>
                    <option value="greeting">Bonjou/Salitasyon</option>
                    <option value="help">Demann Èd</option>
                    <option value="technical">Teknik</option>
                    <option value="programming">Pwogramasyon</option>
                </select>
            </div>
            <div class="form-group">
                <label>Lang:</label>
                <select id="conversationLanguage">
                    <option value="kreyol">Kreyòl</option>
                    <option value="french">Franse</option>
                    <option value="mixed">Melanje</option>
                </select>
            </div>
            <button class="submit-btn" onclick="submitConversation()">💬 Soumèt Konvèsasyon</button>
            <div class="success-message" id="convSuccess"></div>
            <div class="error-message" id="convError"></div>
        </div>
        
        <!-- Submit Code -->
        <div class="training-section">
            <h2>💻 Soumèt Kòd Training</h2>
            <div class="form-group">
                <label>Demann/Prompt:</label>
                <textarea id="codePrompt" placeholder="Egzanp: Kreye yon fonksyon Python pou adisyone 2 nonb"></textarea>
            </div>
            <div class="form-group">
                <label>Kòd:</label>
                <textarea id="codeContent" placeholder="def add(a, b):
    return a + b"></textarea>
            </div>
            <div class="form-group">
                <label>Langaj Pwogramasyon:</label>
                <select id="codeLanguage">
                    <option value="python">Python</option>
                    <option value="javascript">JavaScript</option>
                    <option value="html">HTML</option>
                    <option value="css">CSS</option>
                    <option value="java">Java</option>
                    <option value="cpp">C++</option>
                    <option value="sql">SQL</option>
                </select>
            </div>
            <div class="form-group">
                <label>Deskripsyon (opsyonèl):</label>
                <input type="text" id="codeDescription" placeholder="Egzanp fonksyon adisyon senp">
            </div>
            <button class="submit-btn" onclick="submitCode()">🔧 Soumèt Kòd</button>
            <div class="success-message" id="codeSuccess"></div>
            <div class="error-message" id="codeError"></div>
        </div>
        
        <div class="training-section">
            <p><strong>📌 Nòt:</strong> Tout egzanp ou soumèt yo pral revize anvan yo itilize pou antrene AI a. Mèsi pou kontribisyon ou!</p>
        </div>
    </div>
    
    <script>
        // Load stats
        async function loadStats() {
            try {
                const response = await fetch('/training/stats');
                const data = await response.json();
                
                if (data.success) {
                    const statsHTML = `
                        <div class="stat-card">
                            <div class="stat-number">${data.stats.total_images}</div>
                            <div class="stat-label">Imaj</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">${data.stats.total_videos}</div>
                            <div class="stat-label">Videyo</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">${data.stats.total_conversations}</div>
                            <div class="stat-label">Konvèsasyon</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-number">${data.stats.total_code}</div>
                            <div class="stat-label">Kòd</div>
                        </div>
                    `;
                    document.getElementById('statsGrid').innerHTML = statsHTML;
                }
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }
        
        // Image upload
        const imageUploadArea = document.getElementById('imageUploadArea');
        const imageFile = document.getElementById('imageFile');
        
        imageUploadArea.addEventListener('click', () => imageFile.click());
        
        imageFile.addEventListener('change', (e) => {
            if (e.target.files.length > 0) {
                imageUploadArea.innerHTML = `<p>✅ ${e.target.files[0].name}</p>`;
            }
        });
        
        async function submitImage() {
            const file = imageFile.files[0];
            const description = document.getElementById('imageDescription').value;
            const tags = document.getElementById('imageTags').value;
            
            if (!file || !description) {
                showError('imageError', 'Tanpri chwazi yon imaj epi bay deskripsyon');
                return;
            }
            
            const formData = new FormData();
            formData.append('image', file);
            formData.append('description', description);
            formData.append('tags', tags);
            
            try {
                const response = await fetch('/training/upload-image', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (data.success) {
                    showSuccess('imageSuccess', 'Imaj soumèt avèk siksè! Ap revize li.');
                    // Reset form
                    imageFile.value = '';
                    document.getElementById('imageDescription').value = '';
                    document.getElementById('imageTags').value = '';
                    imageUploadArea.innerHTML = '<p>🖼️ Klike oswa glise imaj la isit</p>';
                    loadStats();
                } else {
                    showError('imageError', data.error);
                }
            } catch (error) {
                showError('imageError', 'Erè nan soumèt imaj la');
            }
        }
        
        async function submitConversation() {
            const userMessage = document.getElementById('userMessage').value;
            const expectedResponse = document.getElementById('expectedResponse').value;
            const category = document.getElementById('conversationCategory').value;
            const language = document.getElementById('conversationLanguage').value;
            
            if (!userMessage || !expectedResponse) {
                showError('convError', 'Tanpri ranpli mesaj ak repons');
                return;
            }
            
            try {
                const response = await fetch('/training/submit-conversation', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        user_message: userMessage,
                        expected_response: expectedResponse,
                        category: category,
                        language: language
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    showSuccess('convSuccess', 'Konvèsasyon soumèt avèk siksè!');
                    // Reset form
                    document.getElementById('userMessage').value = '';
                    document.getElementById('expectedResponse').value = '';
                    loadStats();
                } else {
                    showError('convError', data.error);
                }
            } catch (error) {
                showError('convError', 'Erè nan soumèt konvèsasyon an');
            }
        }
        
        async function submitCode() {
            const prompt = document.getElementById('codePrompt').value;
            const code = document.getElementById('codeContent').value;
            const language = document.getElementById('codeLanguage').value;
            const description = document.getElementById('codeDescription').value;
            
            if (!prompt || !code) {
                showError('codeError', 'Tanpri ranpli prompt ak kòd la');
                return;
            }
            
            try {
                const response = await fetch('/training/submit-code', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        prompt: prompt,
                        code: code,
                        language: language,
                        description: description
                    })
                });
                
                const data = await response.json();
                
                if (data.success) {
                    showSuccess('codeSuccess', 'Kòd soumèt avèk siksè!');
                    // Reset form
                    document.getElementById('codePrompt').value = '';
                    document.getElementById('codeContent').value = '';
                    document.getElementById('codeDescription').value = '';
                    loadStats();
                } else {
                    showError('codeError', data.error);
                }
            } catch (error) {
                showError('codeError', 'Erè nan soumèt kòd la');
            }
        }
        
        function showSuccess(id, message) {
            const el = document.getElementById(id);
            el.textContent = message;
            el.style.display = 'block';
            setTimeout(() => el.style.display = 'none', 5000);
        }
        
        function showError(id, message) {
            const el = document.getElementById(id);
            el.textContent = message;
            el.style.display = 'block';
            setTimeout(() => el.style.display = 'none', 5000);
        }
        
        // Load stats on page load
        loadStats();
    </script>
</body>
</html>
```

## Implementation Files Created

1. `database/training_models.py` - Training database models
2. `routes/training_routes.py` - Training upload/submit routes
3. `models/enhanced_smart_fallback.py` - Smart fallback with user training
4. `templates/training.html` - Training interface
5. `static/js/training.js` - Training functionality

## Benefits

✅ **Community-Driven**: Users improve the AI
✅ **Kreyòl Support**: Better Haitian Creole responses
✅ **Custom Examples**: Real-world scenarios
✅ **Quality Control**: Admin approval system
✅ **Usage Tracking**: See which examples help most
✅ **Progressive Learning**: AI gets better over time

## Next Steps

1. Add training models to database
2. Create training routes
3. Enhance smart fallback with user data
4. Build training interface
5. Add admin approval panel
6. Implement similarity matching
7. Track usage statistics

This creates a collaborative AI that learns from its community!
