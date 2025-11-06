# Facebook Publishing Setup Guide - Glory2YahPub

## Overview
The Facebook publishing feature allows admins to post ads and batches directly to Facebook with one click.

## Features

### 1. **Publish Single Ad to Facebook**
- Post individual approved ads to Facebook page
- Supports images and videos
- Includes ad title, description, price, and WhatsApp contact

### 2. **Publish Batch to Facebook**
- Post multiple ads from a batch at once
- Batch processing with success/failure tracking
- Detailed results page showing which ads published successfully

### 3. **Test Facebook Connection**
- Validate Facebook API credentials
- Check page access and permissions

## Setup Instructions

### Step 1: Create Facebook App

1. Go to [Facebook Developers](https://developers.facebook.com/)
2. Click "My Apps" → "Create App"
3. Choose "Business" as app type
4. Fill in app details and create

### Step 2: Get Page Access Token

1. In your Facebook App dashboard, go to "Tools" → "Graph API Explorer"
2. Select your Facebook Page from the dropdown
3. Add these permissions:
   - `pages_manage_posts`
   - `pages_read_engagement`
   - `publish_video`
4. Click "Generate Access Token"
5. Copy the token (this is temporary)

### Step 3: Get Long-Lived Page Access Token

1. Use the Graph API Explorer or run this command:
```bash
curl -X GET "https://graph.facebook.com/v18.0/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=YOUR_SHORT_LIVED_TOKEN"
```

2. This returns a long-lived user access token
3. Then get the page access token:
```bash
curl -X GET "https://graph.facebook.com/v18.0/me/accounts?access_token=YOUR_LONG_LIVED_USER_TOKEN"
```

4. Find your page in the response and copy its `access_token`

### Step 4: Get Page ID

1. Go to your Facebook Page
2. Click "About"
3. Scroll down to find "Page ID"
4. Or use Graph API Explorer: `GET /me?fields=id,name`

### Step 5: Configure Environment Variables

1. Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

2. Edit `.env` and add your credentials:
```
FACEBOOK_PAGE_ACCESS_TOKEN=your_actual_page_access_token
FACEBOOK_PAGE_ID=your_actual_page_id
```

3. **Important**: Never commit `.env` to version control!

### Step 6: Install Dependencies

The `requests` library is already in requirements.txt, but verify:
```bash
pip install -r requirements.txt
```

## Usage

### Admin Panel Features

#### 1. Test Connection
- Navigate to Admin panel
- Click "Test Facebook Connection" button
- Verifies credentials are valid

#### 2. Publish Single Ad
- In the Ads section, find an approved ad
- Click "Publish to Facebook" button
- Ad will be posted to your Facebook page

#### 3. Publish Batch
- In the Batches section, find a batch
- Click "Publish Batch to Facebook" button
- All ads in the batch will be posted
- View detailed results on the results page

## API Endpoints

### POST `/admin/facebook/publish_ad/<ad_id>`
Publish a single ad to Facebook.

**Requirements:**
- Admin session
- Ad must be approved
- Valid Facebook credentials

**Response:**
- Success: Flash message with confirmation
- Error: Flash message with error details

### POST `/admin/facebook/publish_batch/<batch_id>`
Publish all ads in a batch to Facebook.

**Requirements:**
- Admin session
- Batch must exist
- Ads must be approved
- Valid Facebook credentials

**Response:**
- Success count and failure count
- Redirects to results page

### GET `/admin/facebook/test_connection`
Test Facebook API connection.

**Requirements:**
- Admin session

**Response:**
- Success: Connection OK message
- Error: Error details

### GET `/admin/facebook/batch_results`
View detailed results of last batch publication.

**Requirements:**
- Admin session

**Response:**
- HTML page with success/failure details

## Publishing Behavior

### Single Photo
- Posts as single photo with caption
- Includes ad title, description, price
- Links to app

### Multiple Photos
- Posts as photo album
- Up to 10 photos per ad
- Includes caption with details

### Video
- Posts as video with description
- Includes ad details in description
- May take longer to process

### Text Only
- If no media available
- Posts text with ad details

## Troubleshooting

### "Konfigirasyon Facebook pa konplè"
- Check that `.env` file exists
- Verify `FACEBOOK_PAGE_ACCESS_TOKEN` is set
- Verify `FACEBOOK_PAGE_ID` is set

### "Erè koneksyon Facebook"
- Check internet connection
- Verify access token is valid (not expired)
- Check Facebook API status

### "Ou ka sèlman pibliye piblisite ki apwouve"
- Only approved ads can be published
- Approve the ad first in admin panel

### Token Expired
- Page access tokens can expire
- Generate a new long-lived token
- Update `.env` file

### Permission Errors
- Ensure app has required permissions
- Re-authorize with correct permissions
- Check page role (must be admin/editor)

## Security Notes

1. **Never commit `.env` file** - Add to `.gitignore`
2. **Keep tokens secret** - Don't share or expose
3. **Use long-lived tokens** - They last 60 days
4. **Rotate tokens regularly** - For security
5. **Monitor API usage** - Check Facebook App dashboard

## Rate Limits

Facebook API has rate limits:
- **200 calls per hour** per user
- **4800 calls per day** per app
- Videos may count as multiple calls

**Best Practices:**
- Don't publish too many ads at once
- Space out batch publications
- Monitor rate limit headers

## Testing

### Test with Single Ad
1. Create and approve a test ad
2. Click "Publish to Facebook"
3. Check your Facebook page
4. Verify post appears correctly

### Test with Batch
1. Create a batch with 2-3 ads
2. Click "Publish Batch to Facebook"
3. Check results page
4. Verify all ads posted to Facebook

### Test Connection
1. Click "Test Facebook Connection"
2. Should show success message
3. If error, check credentials

## Files Modified/Created

### New Files:
- ✅ `src/facebook_publisher.py` - Facebook API integration
- ✅ `templates/facebook_batch_results.html` - Results display
- ✅ `.env.example` - Environment configuration template

### Modified Files:
- ✅ `app.py` - Added Facebook publishing routes

## Environment Variables

```bash
# Required
FACEBOOK_PAGE_ACCESS_TOKEN=EAAxxxxxxxxxxxxx  # Long-lived page access token
FACEBOOK_PAGE_ID=123456789012345             # Your Facebook page ID

# Optional
FLASK_ENV=production                          # Flask environment
SECRET_KEY=your_secret_key_here              # Flask secret key
```

## Next Steps

1. **Set up Facebook App** - Follow Step 1-4 above
2. **Configure Environment** - Create `.env` with credentials
3. **Test Connection** - Use test endpoint
4. **Publish Test Ad** - Try with one ad
5. **Publish Batch** - Try with full batch
6. **Monitor Results** - Check Facebook page and results page

## Support

For Facebook API issues:
- [Facebook Developer Docs](https://developers.facebook.com/docs/)
- [Graph API Reference](https://developers.facebook.com/docs/graph-api/)
- [Page Publishing Guide](https://developers.facebook.com/docs/pages/publishing/)

For app issues:
- Check application logs
- Review error messages
- Contact admin: +50942882076

---

**Status**: ✅ Implemented and Ready
**Version**: 1.0
**Last Updated**: 2025-11-06
