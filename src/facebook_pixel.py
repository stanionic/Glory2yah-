import os
import json
from flask import current_app

class FacebookPixel:
    def __init__(self):
        """Initialize Facebook Pixel with Pixel ID from environment variables."""
        self.pixel_id = os.getenv('FACEBOOK_PIXEL_ID', '')

    def is_enabled(self) -> bool:
        """Check if Facebook Pixel is enabled."""
        return bool(self.pixel_id)

    def get_base_code(self) -> str:
        """Get the Facebook Pixel base code for inclusion in HTML head."""
        if not self.is_enabled():
            return ""

        base_code = f"""
<!-- Facebook Pixel Code -->
<script>
  !function(f,b,e,v,n,t,s)
  {{if(f.fbq)return;n=f.fbq=function(){{n.callMethod?
  n.callMethod.apply(n,arguments):n.queue.push(arguments)}};
  if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
  n.queue=[];t=b.createElement(e);t.async=!0;
  t.src=v;s=b.getElementsByTagName(e)[0];
  s.parentNode.insertBefore(t,s)}}(window, document,'script',
  'https://connect.facebook.net/en_US/fbevents.js');
  fbq('init', '{self.pixel_id}');
  fbq('track', 'PageView');
</script>
<noscript><img height="1" width="1" style="display:none"
  src="https://www.facebook.com/tr?id={self.pixel_id}&ev=PageView&noscript=1"
/></noscript>
<!-- End Facebook Pixel Code -->
"""
        return base_code

    def track_batch_view(self, batch_id: str, batch_data: dict = None) -> str:
        """Track when a user views an approved batch."""
        if not self.is_enabled():
            return ""

        event_data = {
            'content_type': 'batch',
            'content_ids': [batch_id],
            'content_name': f'Batch {batch_id}'
        }

        if batch_data:
            event_data.update({
                'content_category': batch_data.get('category', 'approved_batch'),
                'value': batch_data.get('value', 0),
                'currency': 'HTG'
            })

        return self._generate_event_code('ViewContent', event_data)

    def track_batch_purchase(self, batch_id: str, purchase_data: dict = None) -> str:
        """Track when a user makes a purchase from an approved batch."""
        if not self.is_enabled():
            return ""

        event_data = {
            'content_type': 'batch_purchase',
            'content_ids': [batch_id],
            'content_name': f'Batch Purchase {batch_id}'
        }

        if purchase_data:
            event_data.update({
                'value': purchase_data.get('value', 0),
                'currency': purchase_data.get('currency', 'HTG'),
                'num_items': purchase_data.get('num_items', 1)
            })

        return self._generate_event_code('Purchase', event_data)

    def track_batch_interaction(self, batch_id: str, interaction_type: str, interaction_data: dict = None) -> str:
        """Track custom batch interactions (like adding to cart, sharing, etc.)."""
        if not self.is_enabled():
            return ""

        event_data = {
            'content_type': 'batch_interaction',
            'content_ids': [batch_id],
            'content_name': f'Batch {interaction_type} {batch_id}',
            'interaction_type': interaction_type
        }

        if interaction_data:
            event_data.update(interaction_data)

        # Use custom event for interactions
        return self._generate_event_code(f'Batch{interaction_type.title()}', event_data)

    def track_lead_from_batch(self, batch_id: str, lead_data: dict = None) -> str:
        """Track when a user submits a lead/contact from an approved batch."""
        if not self.is_enabled():
            return ""

        event_data = {
            'content_type': 'batch_lead',
            'content_ids': [batch_id],
            'content_name': f'Batch Lead {batch_id}'
        }

        if lead_data:
            event_data.update(lead_data)

        return self._generate_event_code('Lead', event_data)

    def _generate_event_code(self, event_name: str, event_data: dict = None) -> str:
        """Generate JavaScript code for a Facebook Pixel event."""
        if not self.is_enabled():
            return ""

        if event_data:
            data_json = json.dumps(event_data, ensure_ascii=False)
            return f"<script>fbq('track', '{event_name}', {data_json});</script>"
        else:
            return f"<script>fbq('track', '{event_name}');</script>"

# Create singleton instance
facebook_pixel = FacebookPixel()
