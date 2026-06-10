import os
import requests
import logging
from typing import Tuple, List, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

class FacebookPublisher:
    def __init__(self):
        """Initialize Facebook Publisher with credentials from environment variables."""
        self.page_access_token = os.getenv('FACEBOOK_PAGE_ACCESS_TOKEN', '')
        self.page_id = os.getenv('FACEBOOK_PAGE_ID', '')
        self.api_version = 'v18.0'
        self.base_url = f'https://graph.facebook.com/{self.api_version}'
        
    def validate_credentials(self) -> Tuple[bool, str]:
        """
        Validate Facebook credentials.
        Returns: (success: bool, message: str)
        """
        if not self.page_access_token:
            return False, "FACEBOOK_PAGE_ACCESS_TOKEN pa konfigire nan anviwònman an."
        
        if not self.page_id:
            return False, "FACEBOOK_PAGE_ID pa konfigire nan anviwònman an."
        
        try:
            # Test API connection
            url = f"{self.base_url}/me"
            params = {'access_token': self.page_access_token}
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return True, f"Koneksyon Facebook OK! Paj: {data.get('name', 'Unknown')}"
            else:
                error_data = response.json()
                error_msg = error_data.get('error', {}).get('message', 'Unknown error')
                return False, f"Erè koneksyon Facebook: {error_msg}"
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Facebook API connection error: {str(e)}")
            return False, f"Erè koneksyon: {str(e)}"
    
    def publish_ad_to_facebook(self, ad, app_url: str) -> Tuple[bool, str, str]:
        """
        Publish a single ad to Facebook.

        Args:
            ad: Ad object from database
            app_url: Base URL of the application

        Returns:
            (success: bool, message: str, post_id: str)
        """
        if not self.page_access_token or not self.page_id:
            return False, "Konfigirasyon Facebook pa konplè.", ""

        try:
            # Prepare ad URL
            ad_url = f"{app_url}/achte"

            # Prepare message
            message = f"🎯 {ad.title}\n\n"
            message += f"📝 {ad.description}\n\n"

            if ad.ad_type == 'sell':
                message += f"💰 Pri: {ad.price_gkach} Gkach\n\n"

            message += f"🔗 Wè plis detay: {ad_url}\n"
            message += f"📱 Kontakte nou sou WhatsApp: {ad.user_whatsapp}"

            # Prepare media
            media_urls = []
            if ad.media_type == 'images' and ad.images:
                image_list = ad.images.split(',')
                for img in image_list[:10]:  # Facebook allows max 10 images
                    media_urls.append(f"{app_url}/static/uploads/{img.strip()}")
            elif ad.media_type == 'video' and ad.video:
                media_urls.append(f"{app_url}/static/uploads/{ad.video}")

            # Publish based on media type
            if ad.media_type == 'video' and media_urls:
                # Publish video
                post_id = self._publish_video(message, media_urls[0])
            elif media_urls:
                # Publish photos
                if len(media_urls) == 1:
                    post_id = self._publish_single_photo(message, media_urls[0])
                else:
                    post_id = self._publish_multiple_photos(message, media_urls)
            else:
                # Publish text only
                post_id = self._publish_text(message)

            if post_id:
                return True, "Piblisite pibliye sou Facebook avèk siksè!", post_id
            else:
                return False, "Erè nan pibliyasyon Facebook.", ""

        except Exception as e:
            logger.error(f"Error publishing ad to Facebook: {str(e)}")
            return False, f"Erè: {str(e)}", ""

    def publish_video_to_facebook(self, video_path: str, message: str) -> Tuple[bool, str, str]:
        """
        Publish a video file to Facebook.

        Args:
            video_path: Path to the video file
            message: Message to post with the video

        Returns:
            (success: bool, message: str, post_id: str)
        """
        if not self.page_access_token or not self.page_id:
            return False, "Konfigirasyon Facebook pa konplè.", ""

        try:
            # Check if video_path is a URL or local file
            if video_path.startswith('http'):
                # It's a URL, use the existing _publish_video method
                post_id = self._publish_video(message, video_path)
            else:
                # It's a local file path, upload directly
                post_id = self._publish_video_file(message, video_path)

            if post_id:
                return True, "Videyo pibliye sou Facebook avèk siksè!", post_id
            else:
                return False, "Erè nan pibliyasyon videyo Facebook.", ""

        except Exception as e:
            logger.error(f"Error publishing video to Facebook: {str(e)}")
            return False, f"Erè: {str(e)}", ""
    
    def _publish_text(self, message: str) -> str:
        """Publish text-only post."""
        try:
            url = f"{self.base_url}/{self.page_id}/feed"
            data = {
                'message': message,
                'access_token': self.page_access_token
            }
            
            response = requests.post(url, data=data, timeout=30)
            
            if response.status_code == 200:
                return response.json().get('id', '')
            else:
                logger.error(f"Facebook API error: {response.text}")
                return ""
                
        except Exception as e:
            logger.error(f"Error publishing text: {str(e)}")
            return ""
    
    def _publish_single_photo(self, message: str, photo_url: str) -> str:
        """Publish single photo post."""
        try:
            url = f"{self.base_url}/{self.page_id}/photos"
            data = {
                'message': message,
                'url': photo_url,
                'access_token': self.page_access_token
            }
            
            response = requests.post(url, data=data, timeout=30)
            
            if response.status_code == 200:
                return response.json().get('id', '')
            else:
                logger.error(f"Facebook API error: {response.text}")
                return ""
                
        except Exception as e:
            logger.error(f"Error publishing photo: {str(e)}")
            return ""
    
    def _publish_multiple_photos(self, message: str, photo_urls: List[str]) -> str:
        """Publish multiple photos as album."""
        try:
            # Step 1: Upload photos without publishing
            photo_ids = []
            for photo_url in photo_urls:
                url = f"{self.base_url}/{self.page_id}/photos"
                data = {
                    'url': photo_url,
                    'published': 'false',
                    'access_token': self.page_access_token
                }
                
                response = requests.post(url, data=data, timeout=30)
                if response.status_code == 200:
                    photo_ids.append({'media_fbid': response.json().get('id')})
            
            if not photo_ids:
                return ""
            
            # Step 2: Publish all photos together
            url = f"{self.base_url}/{self.page_id}/feed"
            data = {
                'message': message,
                'attached_media': photo_ids,
                'access_token': self.page_access_token
            }
            
            response = requests.post(url, json=data, timeout=30)
            
            if response.status_code == 200:
                return response.json().get('id', '')
            else:
                logger.error(f"Facebook API error: {response.text}")
                return ""
                
        except Exception as e:
            logger.error(f"Error publishing multiple photos: {str(e)}")
            return ""
    
    def _publish_video(self, message: str, video_url: str) -> str:
        """Publish video post."""
        try:
            url = f"{self.base_url}/{self.page_id}/videos"
            data = {
                'description': message,
                'file_url': video_url,
                'access_token': self.page_access_token
            }

            response = requests.post(url, data=data, timeout=60)

            if response.status_code == 200:
                return response.json().get('id', '')
            else:
                logger.error(f"Facebook API error: {response.text}")
                return ""

        except Exception as e:
            logger.error(f"Error publishing video: {str(e)}")
            return ""

    def _publish_video_file(self, message: str, video_path: str) -> str:
        """Publish video file directly (for local files)."""
        try:
            url = f"{self.base_url}/{self.page_id}/videos"
            with open(video_path, 'rb') as video_file:
                files = {'source': video_file}
                data = {
                    'description': message,
                    'access_token': self.page_access_token
                }

                response = requests.post(url, data=data, files=files, timeout=120)

            if response.status_code == 200:
                return response.json().get('id', '')
            else:
                logger.error(f"Facebook API error: {response.text}")
                return ""

        except Exception as e:
            logger.error(f"Error publishing video file: {str(e)}")
            return ""
    
    def publish_batch_to_facebook(self, ads: List, app_url: str) -> Dict:
        """
        Publish multiple ads to Facebook as a batch.
        
        Args:
            ads: List of Ad objects
            app_url: Base URL of the application
            
        Returns:
            Dictionary with 'successful' and 'failed' lists
        """
        results = {
            'successful': [],
            'failed': [],
            'timestamp': datetime.now().isoformat()
        }
        
        for ad in ads:
            success, message, post_id = self.publish_ad_to_facebook(ad, app_url)
            
            if success:
                results['successful'].append({
                    'ad_id': ad.ad_id,
                    'title': ad.title,
                    'post_id': post_id,
                    'message': message
                })
            else:
                results['failed'].append({
                    'ad_id': ad.ad_id,
                    'title': ad.title,
                    'error': message
                })
        
        return results

# Create singleton instance
facebook_publisher = FacebookPublisher()
