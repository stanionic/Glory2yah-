# Refactoring Plan: Proper Delivery Table Usage with Messaging

## Current Issues
1. Using `CartItem.negotiation_status` for delivery flow (should use `Delivery` table)
2. No proper messaging system between buyer and seller during negotiation
3. Delivery records created only at checkout (should be created when buyer submits cart)

## Proposed Architecture

### Database Flow

#### Phase 1: Buyer Submits Cart
- Buyer adds items to `CartItem` table (existing)
- Buyer submits cart with delivery address
- **Create `Delivery` record:**
  - `status = 'pending'` (waiting for seller to set shipping)
  - `delivery_cost = 0` (not set yet)
  - `cart_items` = JSON of all cart items
  - `delivery_address` = buyer's address
  - Link delivery_id to cart items

#### Phase 2: Seller Sets Shipping Price
- Seller accesses delivery via `delivery_id`
- Seller sets `delivery_cost`
- Update `status = 'price_set'`
- Notify buyer with link to confirm/decline

#### Phase 3: Buyer Confirms or Declines
- Buyer views delivery with updated price
- **Confirm:** `status = 'confirmed'` → proceed to checkout
- **Decline:** `status = 'declined'` → clear cart and delivery

#### Phase 4: Messaging (Optional during negotiation)
- Use existing `Message` table
- Buyer and seller can exchange messages linked to `delivery_id`
- Messages displayed in delivery view pages

### Files to Modify

1. **models.py** (if needed)
   - Verify Delivery model has all needed fields
   - Add any missing fields

2. **app.py**
   - `shopping_card_update` route: Create Delivery record when buyer submits
   - `seller_update_cart` route: Update Delivery record (not CartItem)
   - `checkout` route: Use Delivery records instead of CartItem
   - Add new routes for messaging

3. **templates/shopping_card_update.html**
   - Add messaging interface for buyer
   - Display delivery status

4. **templates/seller_update_cart.html**
   - Add messaging interface for seller
   - Display delivery details from Delivery table

5. **New template: delivery_messages.html** (optional)
   - Dedicated page for buyer-seller communication

## Implementation Steps

### Step 1: Update `shopping_card_update` route
- [x] When buyer submits (mode='enter_shipping'):
  - Create Delivery record with status='pending'
  - Store cart items in delivery.cart_items JSON
  - Link delivery_id to notification

### Step 2: Update `seller_update_cart` route
- [x] Load Delivery record instead of CartItem
- [x] Update delivery_cost in Delivery table
- [x] Set status='price_set'
- [x] Send notification with delivery_id

### Step 3: Update buyer confirmation flow
- [x] Load Delivery record to show updated price
- [x] Confirm: Update status='confirmed', proceed to checkout
- [x] Decline: Update status='declined', clear cart

### Step 4: Update `checkout` route
- [x] Use Delivery records with status='confirmed'
- [x] Process payment and complete delivery

### Step 5: Implement Messaging
- [x] Add message form to buyer and seller views
- [x] Use existing Message table and communication.py functions
- [x] Display messages in delivery views

### Step 6: Testing
- [ ] Test complete flow end-to-end
- [ ] Test messaging functionality
- [ ] Test edge cases (decline, multiple items, etc.)

## Benefits of This Approach

1. ✅ Proper separation of concerns (Cart vs Delivery)
2. ✅ Better tracking of delivery status
3. ✅ Enables buyer-seller communication
4. ✅ Cleaner code and easier to maintain
5. ✅ Follows database design best practices
6. ✅ Delivery can be pending while buyer and seller negotiate

## Migration Notes

- Existing CartItem records will still work for cart management
- Delivery table will handle the delivery negotiation process
- No database schema changes needed (tables already exist)
