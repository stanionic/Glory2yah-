import os
import requests
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class FacebookAdsManager:
    def __init__(self):
        self.access_token = os.environ.get('FACEBOOK_ACCESS_TOKEN') or os.environ.get('FACEBOOK_PAGE_ACCESS_TOKEN')
        self.ad_account_id = os.environ.get('FACEBOOK_AD_ACCOUNT_ID')
        self.page_id = os.environ.get('FACEBOOK_PAGE_ID')
        self.api_version = 'v18.0'
        self.base_url = f"https://graph.facebook.com/{self.api_version}"

    def validate_config(self):
        if not self.access_token:
            return False, "Missing FACEBOOK_ACCESS_TOKEN"
        if not self.ad_account_id:
            return False, "Missing FACEBOOK_AD_ACCOUNT_ID"
        if not self.page_id:
            return False, "Missing FACEBOOK_PAGE_ID"
        return True, "Configuration OK"

    def create_campaign(self, name):
        url = f"{self.base_url}/act_{self.ad_account_id}/campaigns"
        params = {
            'name': name,
            'objective': 'OUTCOME_TRAFFIC',
            'status': 'PAUSED', # Create paused for safety
            'special_ad_categories': [],
            'access_token': self.access_token
        }
        response = requests.post(url, json=params)
        if response.status_code == 200:
            return response.json().get('id')
        logger.error(f"Failed to create campaign: {response.text}")
        return None

    def create_ad_set(self, campaign_id, name):
        url = f"{self.base_url}/act_{self.ad_account_id}/adsets"
        # Default targeting: Haiti, Age 18-65+
        params = {
            'name': name,
            'campaign_id': campaign_id,
            'daily_budget': 100, # USD cents, e.g. $1.00
            'billing_event': 'IMPRESSIONS',
            'optimization_goal': 'LINK_CLICKS',
            'bid_strategy': 'LOWEST_COST_WITHOUT_CAP',
            'targeting': {
                'geo_locations': {'countries': ['HT']},
                'age_min': 18,
                'age_max': 65,
            },
            'start_time': datetime.utcnow().isoformat(),
            'status': 'PAUSED',
            'access_token': self.access_token
        }
        response = requests.post(url, json=params)
        if response.status_code == 200:
            return response.json().get('id')
        logger.error(f"Failed to create ad set: {response.text}")
        return None

    def upload_image(self, image_path):
        url = f"{self.base_url}/act_{self.ad_account_id}/adimages"
        with open(image_path, 'rb') as img_file:
            files = {'file': img_file}
            params = {'access_token': self.access_token}
            response = requests.post(url, files=files, data=params)
        
        if response.status_code == 200:
            data = response.json()
            # Response format: {"images": {"filename": {"hash": "...", "url": "..."}}}
            images = data.get('images', {})
            if images:
                first_key = list(images.keys())[0]
                return images[first_key].get('hash')
        logger.error(f"Failed to upload image: {response.text}")
        return None

    def create_ad_creative(self, name, image_hash, link_url, message):
        url = f"{self.base_url}/act_{self.ad_account_id}/adcreatives"
        params = {
            'name': name,
            'object_story_spec': {
                'page_id': self.page_id,
                'link_data': {
                    'image_hash': image_hash,
                    'link': link_url,
                    'message': message,
                    'call_to_action': {
                        'type': 'LEARN_MORE',
                        'value': {'link': link_url}
                    }
                }
            },
            'access_token': self.access_token
        }
        response = requests.post(url, json=params)
        if response.status_code == 200:
            return response.json().get('id')
        logger.error(f"Failed to create ad creative: {response.text}")
        return None

    def create_ad(self, ad_set_id, creative_id, name):
        url = f"{self.base_url}/act_{self.ad_account_id}/ads"
        params = {
            'name': name,
            'adset_id': ad_set_id,
            'creative': {'creative_id': creative_id},
            'status': 'PAUSED',
            'access_token': self.access_token
        }
        response = requests.post(url, json=params)
        if response.status_code == 200:
            return response.json().get('id')
        logger.error(f"Failed to create ad: {response.text}")
        return None

    def create_full_ad_campaign(self, batch_id, image_path, landing_page_url, ad_text):
        """
        Orchestrates the creation of a full ad campaign for a batch.
        """
        valid, msg = self.validate_config()
        if not valid:
            logger.warning(f"Skipping Facebook Ads creation: {msg}")
            return None

        logger.info(f"Starting Facebook Ad creation for Batch {batch_id}")

        # 1. Create Campaign
        campaign_id = self.create_campaign(f"Batch {batch_id} Campaign")
        if not campaign_id: return None

        # 2. Create Ad Set
        ad_set_id = self.create_ad_set(campaign_id, f"Batch {batch_id} AdSet")
        if not ad_set_id: return None

        # 3. Upload Image
        image_hash = self.upload_image(image_path)
        if not image_hash: return None

        # 4. Create Creative
        creative_id = self.create_ad_creative(f"Batch {batch_id} Creative", image_hash, landing_page_url, ad_text)
        if not creative_id: return None

        # 5. Create Ad
        ad_id = self.create_ad(ad_set_id, creative_id, f"Batch {batch_id} Ad")
        
        if ad_id:
            logger.info(f"Successfully created Facebook Ad: {ad_id}")
            return ad_id
        return None
