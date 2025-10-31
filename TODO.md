# Shopping Cart with Seller-Set Shipping Fees - Implementation Plan

## Current Status
- Analyzed existing Glory2yahPub project
- Identified current single-product cart system
- Planned modifications for multiple products from same seller

## Requirements
1. Buyer Flow:
   - Add multiple products of same seller to cart
   - Enter shipping address and WhatsApp number
   - Review cart before purchase

2. Seller Flow:
   - Receive buyer’s cart and WhatsApp contact automatically
   - Set or update shipping fees for each buyer’s order
   - Send the updated cart/invoice back to the buyer via WhatsApp or web dashboard

3. Buyer Confirmation:
   - Receive updated cart with shipping fees
   - Confirm order and proceed to payment

4. System Requirements:
   - Use WhatsApp links to communicate between buyer and seller
   - Maintain mobile-responsive interface
   - Show visual cues for pending shipping approval or updates
   - Optional: integrate multiple payment methods
   - Keep the cart and user info in a database (SQLite, PostgreSQL, or NoSQL)

## Implementation Steps

### Phase 1: Database Model Updates
- [ ] Modify Delivery model to support multiple ads (JSON field for cart items)
- [ ] Add Cart/CartItem models if needed for better structure
- [ ] Update database schema and migration

### Phase 2: Backend Logic Updates
- [ ] Update shopping_cart route to handle multiple items
- [ ] Modify check_balance route for cart totals
- [ ] Update buy_ad route for multiple item purchases
- [ ] Add seller dashboard route for managing deliveries
- [ ] Update set_delivery route for cart-based fees

### Phase 3: Frontend Template Updates
- [ ] Update shopping_cart.html to display multiple items
- [ ] Modify check_balance.html for cart summary
- [ ] Update cart_success.html for multiple items
- [ ] Create seller dashboard template
- [ ] Update set_delivery.html for cart items

### Phase 4: WhatsApp Communication Updates
- [ ] Update notifications for multiple cart items
- [ ] Add seller dashboard access link in WhatsApp messages
- [ ] Ensure proper cart details in all notifications

### Phase 5: Testing and Validation
- [ ] Test cart functionality with multiple items
- [ ] Verify WhatsApp communication
- [ ] Test seller dashboard access
- [ ] Validate database relationships
- [ ] Test payment flow with shipping fees

## Files to Modify
- models.py: Delivery/Cart models
- app.py: Routes and logic
- templates/: All cart-related templates
- src/notifications.py: WhatsApp messages
- static/css/: Styling updates

## Additional Requirements
- Add seller access dashboard or send URL via WhatsApp to allow sellers to set shipping fees in buyer shopping cart
