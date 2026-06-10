═══════════════════════════════════════════════════════════════════════════════
                    GLORY2YAHPUB - COMPLETE REBUILD PLAN
                  From Messy PoC to Production-Ready Platform
═══════════════════════════════════════════════════════════════════════════════

PHASE 1: CODEBASE CLEANUP & AUDIT
═════════════════════════════════════════════════════════════════════════════

CURRENT STATE ANALYSIS:
- 2000+ files across multiple sub-applications
- 8 separate Flask apps (dok/, ecole_biblique/, GlorYah_IA/, mennenm/, party/, etc.)
- Massive code duplication
- Unused dependencies
- Dead code everywhere
- Inconsistent patterns

FILES TO DELETE (CLEANUP):
────────────────────────────

ENTIRE DIRECTORIES (Not part of core Glory2YahPub):
✗ /dok/ - Separate AI app (REMOVE)
✗ /ecole_biblique/ - School platform (REMOVE)
✗ /GlorYah_IA/ - AI app (REMOVE)
✗ /mennenm/ - Delivery app (REMOVE)
✗ /party/ - Party app (REMOVE)
✗ /student_registration_platform/ - Separate app (REMOVE)
✗ /konferans/ - Conference app (REMOVE)
✗ /.qodo/ - IDE config (REMOVE)
✗ /.sixth/ - IDE config (REMOVE)
✗ /src/ - Unused utilities (REMOVE)

REASON: These are separate applications, not part of Glory2YahPub core.
They bloat the codebase and create confusion.

ROOT LEVEL FILES TO DELETE:
✗ cloudflared.exe - Unused binary
✗ glory2yahpub_demo.mp4 - Demo video (move to docs/)
✗ temp_video_section.html - Temporary file
✗ All AUDIT_*.md files - Move to /docs/audit/
✗ All CRITICAL_FIXES_*.md - Move to /docs/
✗ All PRODUCTION_*.md - Move to /docs/
✗ All *_SUMMARY.md - Move to /docs/
✗ All *_REPORT_*.md - Move to /docs/
✗ All *_CHECKLIST.md - Move to /docs/
✗ All *_GUIDE.md - Move to /docs/
✗ All *_INDEX.md - Move to /docs/
✗ All *_LIST.md - Move to /docs/
✗ All *.bat files (except START.bat) - Move to /scripts/
✗ All *.ps1 files - Move to /scripts/
✗ All test_*.py files - Move to /tests/
✗ All debug_*.py files - Move to /tests/
✗ All fix_*.py files - Move to /scripts/
✗ All run_*.py files - Move to /scripts/
✗ All check_*.py files - Move to /scripts/
✗ All init_*.py files - Move to /scripts/
✗ All verify_*.py files - Move to /scripts/
✗ All add_*.py files - Move to /scripts/
✗ All migrate_*.py files - Move to /scripts/
✗ All tunnel.py - Move to /scripts/
✗ All utils.py (root level) - Move to /app/utils/
✗ All config.py (root level) - Move to /app/config.py
✗ All models.py (root level) - Move to /app/models/
✗ All app.py (root level) - Replace with app_clean.py

TEMPLATES TO CONSOLIDATE:
────────────────────────

KEEP (Core Glory2YahPub):
✓ /templates/auth/ - Login/Register
✓ /templates/cart/ - Shopping cart
✓ /templates/delivery/ - Delivery management
✓ /templates/gkach/ - Wallet
✓ /templates/components/ - Reusable components
✓ /templates/base.html - Base template
✓ /templates/index.html - Home feed
✓ /templates/ad_detail.html - Product detail
✓ /templates/profile.html - User profile
✓ /templates/admin.html - Admin dashboard

DELETE (Sub-apps):
✗ /templates/dok/
✗ /templates/ecole_biblique/
✗ /templates/gloryah_ia/
✗ /templates/konferans/
✗ /templates/mennenm/
✗ /templates/party/
✗ /templates/tchat_ave_m/
✗ All *_backup.html files
✗ All *_old.html files
✗ All *_test.html files

STATIC FILES CLEANUP:
────────────────────

KEEP:
✓ /static/css/style.css - Main styles
✓ /static/css/mobile-first.css - Mobile styles
✓ /static/js/script.js - Main JS
✓ /static/js/mobile-first.js - Mobile JS
✓ /static/images/ - Logo and assets
✓ /static/uploads/ - User uploads
✓ /static/manifest.json - PWA manifest
✓ /static/sw.js - Service worker

DELETE:
✗ /static/css/ad-rating.css - Move to components
✗ /static/css/dok_style.css - Sub-app
✗ /static/css/video-enhancements.css - Unused
✗ /static/js/ad-rating.js - Move to components
✗ /static/js/hebergement.py - Wrong location
✗ /static/js/video-autoplay.js - Unused
✗ /static/recordings/ - User data (archive separately)

DEPENDENCIES CLEANUP:
────────────────────

CURRENT requirements.txt likely has:
- Unused ML libraries (torch, tensorflow)
- Unused AI libraries
- Duplicate packages
- Old versions

CLEAN requirements.txt:
```
Flask==2.3.3
Flask-SQLAlchemy==3.0.5
Flask-CORS==4.0.0
Flask-Limiter==3.5.0
python-dotenv==1.0.0
Werkzeug==2.3.7
SQLAlchemy==2.0.20
psycopg2-binary==2.9.7
redis==5.0.0
celery==5.3.1
Pillow==10.0.0
requests==2.31.0
gunicorn==21.2.0
```

═════════════════════════════════════════════════════════════════════════════
PHASE 2: NEW CLEAN ARCHITECTURE
═════════════════════════════════════════════════════════════════════════════

NEW DIRECTORY STRUCTURE:

glory2yahpub/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py
│   │   ├── ad.py
│   │   ├── cart.py
│   │   ├── delivery.py
│   │   ├── gkach.py
│   │   └── share.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── main.py
│   │   ├── ads.py
│   │   ├── cart.py
│   │   ├── delivery.py
│   │   ├── gkach.py
│   │   └── share.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── ad_service.py
│   │   ├── cart_service.py
│   │   ├── delivery_service.py
│   │   ├── gkach_service.py
│   │   └── share_service.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── validators.py
│   │   ├── security.py
│   │   ├── media.py
│   │   └── decorators.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── auth/
│   │   ├── ads/
│   │   ├── cart/
│   │   ├── delivery/
│   │   ├── gkach/
│   │   ├── profile/
│   │   └── components/
│   └── static/
│       ├── css/
│       ├── js/
│       ├── images/
│       └── uploads/
├── migrations/
├── tests/
├── scripts/
├── docs/
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
├── wsgi.py
└── README.md

═════════════════════════════════════════════════════════════════════════════
PHASE 3: DATABASE MODELS (CLEAN)
═════════════════════════════════════════════════════════════════════════════

Core Models:

1. User
   - id (PK)
   - whatsapp (unique)
   - email (unique)
   - name
   - password_hash
   - profile_photo
   - bio
   - is_active
   - is_admin
   - created_at
   - updated_at
   - deleted_at (soft delete)

2. Ad
   - ad_id (PK, UUID)
   - user_id (FK)
   - title
   - description
   - images (JSON array)
   - video
   - price_gkach
   - admin_status (under_review, approved, rejected)
   - payment_status (pending, completed)
   - like_count
   - view_count
   - share_count
   - average_rating
   - rating_count
   - created_at
   - updated_at
   - deleted_at

3. AdComment
   - id (PK)
   - ad_id (FK)
   - user_id (FK)
   - comment
   - created_at

4. AdRating
   - id (PK)
   - ad_id (FK)
   - user_id (FK)
   - rating (1-5)
   - created_at

5. CartItem
   - id (PK)
   - user_id (FK)
   - ad_id (FK)
   - quantity
   - shipping_fee
   - created_at
   - updated_at

6. Delivery
   - delivery_id (PK, UUID)
   - user_id (FK)
   - seller_id (FK)
   - ad_id (FK)
   - total_price
   - status (pending, confirmed, shipped, delivered)
   - delivery_address
   - created_at
   - delivered_at

7. UserGkach
   - id (PK)
   - user_id (FK)
   - balance
   - created_at
   - updated_at

8. GkachTransaction
   - id (PK)
   - user_id (FK)
   - type (share_reward, sale_commission, purchase, withdrawal)
   - amount
   - description
   - created_at

9. AdShare
   - id (PK)
   - ad_id (FK)
   - user_id (FK)
   - share_link (unique)
   - click_count
   - reward_claimed
   - created_at

10. AdShareClick
    - id (PK)
    - share_id (FK)
    - ip_address
    - created_at

═════════════════════════════════════════════════════════════════════════════
PHASE 4: MOBILE-FIRST UI/UX REDESIGN
═════════════════════════════════════════════════════════════════════════════

NAVIGATION STRUCTURE:

Bottom Navigation Bar (Sticky):
┌─────────────────────────────────────────┐
│  🏠 Home  │  🛒 Market  │  ➕ Create  │  🔔 Notify  │  👤 Profile  │
└─────────────────────────────────────────┘

HOME FEED (Facebook + TikTok Style):
┌─────────────────────────────────────────┐
│ Stories (Horizontal Scroll)             │
│ [Ad1] [Ad2] [Ad3] [Ad4] [Ad5]          │
└─────────────────────────────────────────┘
│ Feed (Infinite Scroll)                  │
│ ┌─────────────────────────────────────┐ │
│ │ User Avatar  Username  ⋮            │ │
│ │ Ad Image                            │ │
│ │ ❤️ 234  💬 12  ↗️ 45  ⋯             │ │
│ │ "Amazing product!"                  │ │
│ └─────────────────────────────────────┘ │
│ ┌─────────────────────────────────────┐ │
│ │ [Next Ad Card]                      │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘

MARKETPLACE (AliExpress Style):
┌─────────────────────────────────────────┐
│ Search Bar                              │
│ [Filter] [Sort]                         │
├─────────────────────────────────────────┤
│ ┌──────────────┐  ┌──────────────┐     │
│ │ Product 1    │  │ Product 2    │     │
│ │ [Image]      │  │ [Image]      │     │
│ │ $50 Gkach    │  │ $75 Gkach    │     │
│ │ ⭐⭐⭐⭐⭐ (234) │  │ ⭐⭐⭐⭐ (156)  │     │
│ │ [Add to Cart]│  │ [Add to Cart]│     │
│ └──────────────┘  └──────────────┘     │
│ ┌──────────────┐  ┌──────────────┐     │
│ │ Product 3    │  │ Product 4    │     │
│ │ [Image]      │  │ [Image]      │     │
│ │ $30 Gkach    │  │ $100 Gkach   │     │
│ │ ⭐⭐⭐⭐⭐ (512) │  │ ⭐⭐⭐⭐⭐ (789)  │     │
│ │ [Add to Cart]│  │ [Add to Cart]│     │
│ └──────────────┘  └──────────────┘     │
└─────────────────────────────────────────┘

PRODUCT DETAIL (Fullscreen Mobile):
┌─────────────────────────────────────────┐
│ ← [Image Carousel - Swipeable]          │
│ [Image 1] [Image 2] [Image 3]           │
│ ⭐⭐⭐⭐⭐ (234 reviews)                    │
├─────────────────────────────────────────┤
│ Product Title                           │
│ $50 Gkach                               │
│ In Stock                                │
├─────────────────────────────────────────┤
│ Description                             │
│ Lorem ipsum dolor sit amet...           │
├─────────────────────────────────────────┤
│ Seller: John Doe                        │
│ ⭐⭐⭐⭐⭐ (98% positive)                   │
│ 📍 Port-au-Prince                       │
├─────────────────────────────────────────┤
│ Shipping: Free                          │
│ Delivery: 2-3 days                      │
├─────────────────────────────────────────┤
│ [Sticky Button]                         │
│ ┌─────────────────────────────────────┐ │
│ │ [Add to Cart] [Buy Now]             │ │
│ └─────────────────────────────────────┘ │
└─────────────────────────────────────────┘

CHECKOUT FLOW:
1. Review Cart
   - Product list
   - Quantities
   - Total price
   - [Edit] [Proceed]

2. Shipping Address
   - Address input
   - City/Region
   - [Confirm]

3. Seller Confirmation
   - Seller updates shipping fee
   - User confirms
   - [Proceed to Payment]

4. Payment (Login Required)
   - Gkach balance check
   - Confirm purchase
   - [Pay Now]

5. Order Confirmation
   - Order number
   - Tracking link
   - [View Order]

═════════════════════════════════════════════════════════════════════════════
PHASE 5: MONETIZATION & REWARD SYSTEM
═════════════════════════════════════════════════════════════════════════════

VIRAL SHARING SYSTEM:

1. Share Ad Externally
   - User clicks "Share" on ad
   - Generates unique referral link
   - Can share on WhatsApp, Facebook, etc.
   - Tracks clicks

2. Click Tracking
   - Each click recorded
   - IP + User Agent logged
   - Fraud detection (same IP multiple clicks)

3. Reward System
   - 100 clicks = 10 Gkach
   - 2% commission on sales through referral link
   - Real-time wallet update

4. User Wallet Dashboard
   - Total Gkach balance
   - Pending rewards
   - Completed sales
   - Click history
   - Withdrawal requests

IMPLEMENTATION:

AdShare Model:
- share_id (unique link)
- ad_id
- user_id
- click_count
- reward_claimed
- reward_amount

AdShareClick Model:
- share_id
- ip_address
- user_agent
- created_at

GkachTransaction Model:
- user_id
- type (share_reward, sale_commission)
- amount
- description
- created_at

═════════════════════════════════════════════════════════════════════════════
PHASE 6: PERFORMANCE OPTIMIZATION
═════════════════════════════════════════════════════════════════════════════

LOAD TIME TARGETS:
- First Paint: <1.5s
- First Contentful Paint: <2.5s
- Time to Interactive: <3s
- Lighthouse Score: 90+

OPTIMIZATION STRATEGIES:

1. Image Optimization
   - WebP format with fallback
   - Lazy loading
   - Responsive images
   - Image compression

2. Code Splitting
   - Separate JS bundles per page
   - Async loading
   - Minimal JS on home page

3. Caching
   - Redis for session/query caching
   - HTTP caching headers
   - Service worker for offline

4. Database
   - Query optimization
   - Indexes on frequently queried columns
   - Connection pooling

5. CDN
   - Static assets on CDN
   - Image delivery via CDN
   - Gzip compression

═════════════════════════════════════════════════════════════════════════════
PHASE 7: MODERN DESIGN SYSTEM
═════════════════════════════════════════════════════════════════════════════

DESIGN TOKENS:

Colors:
- Primary: #667eea (Purple)
- Secondary: #764ba2 (Dark Purple)
- Success: #10b981 (Green)
- Warning: #f59e0b (Amber)
- Error: #ef4444 (Red)
- Neutral: #f3f4f6 (Light Gray)

Typography:
- Font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto
- H1: 32px, 700
- H2: 24px, 700
- H3: 20px, 600
- Body: 16px, 400
- Small: 14px, 400

Spacing:
- xs: 4px
- sm: 8px
- md: 16px
- lg: 24px
- xl: 32px

Shadows:
- sm: 0 1px 2px rgba(0,0,0,0.05)
- md: 0 4px 6px rgba(0,0,0,0.1)
- lg: 0 10px 15px rgba(0,0,0,0.1)

Border Radius:
- sm: 4px
- md: 8px
- lg: 12px
- full: 9999px

COMPONENTS:

Button:
- Primary (filled)
- Secondary (outline)
- Tertiary (ghost)
- Sizes: sm, md, lg
- States: default, hover, active, disabled

Card:
- Rounded corners (12px)
- Subtle shadow
- Padding: 16px
- Hover effect

Input:
- Border: 1px solid #e5e7eb
- Padding: 12px
- Border radius: 8px
- Focus: blue outline

Badge:
- Rounded (full)
- Sizes: sm, md
- Colors: primary, success, warning, error

Skeleton Loader:
- Animated gradient
- Matches content shape
- Smooth transition

═════════════════════════════════════════════════════════════════════════════
PHASE 8: PWA IMPLEMENTATION
═════════════════════════════════════════════════════════════════════════════

manifest.json:
```json
{
  "name": "Glory2YahPub",
  "short_name": "G2Y",
  "description": "Modern Social Commerce Platform for Haiti",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#667eea",
  "icons": [
    {
      "src": "/static/images/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/static/images/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
```

Service Worker:
- Cache static assets
- Offline fallback
- Background sync
- Push notifications

═════════════════════════════════════════════════════════════════════════════
IMPLEMENTATION TIMELINE
═════════════════════════════════════════════════════════════════════════════

Week 1: Cleanup & Architecture
- Delete unused files/folders
- Create new clean structure
- Set up models
- Set up routes

Week 2: Core Features
- Authentication
- Ad listing
- Ad detail
- Shopping cart

Week 3: Monetization
- Gkach system
- Share tracking
- Reward system
- Wallet

Week 4: UI/UX
- Mobile-first redesign
- Component library
- Responsive design
- Performance optimization

Week 5: Polish & Deploy
- Testing
- Bug fixes
- PWA setup
- Deployment

═════════════════════════════════════════════════════════════════════════════
DELIVERABLES
═════════════════════════════════════════════════════════════════════════════

✓ Clean, modular codebase
✓ Removed files list (with reasons)
✓ Fixed bugs list
✓ New architecture documentation
✓ Mobile-first UI/UX redesign
✓ Fully functional reward system
✓ Optimized performance
✓ Updated requirements.txt
✓ Comprehensive README
✓ PWA setup
✓ Deployment guide

═════════════════════════════════════════════════════════════════════════════
