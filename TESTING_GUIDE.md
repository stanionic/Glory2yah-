# Testing Guide - Glory2YahPub Checkout Flow

## Prerequisites

1. **Install Dependencies:**
```bash
pip install -r requirements.txt
```

2. **Create .env File:**
Create a `.env` file in the root directory with:
```
SECRET_KEY=your-secret-key-here
ADMIN_PASSWORD=your-admin-password
ADMIN_WHATSAPP=+50942882076
```

3. **Run the Application:**
```bash
python app.py
```

---

## Test Scenario 1: Complete Checkout Flow (NEW DELIVERY-BASED)

### Step 1: Buyer Adds Items to Cart
1. Go to `/achte` (shopping page)
2. Find an approved ad
3. Click "Ajoute nan Panier" (Add to Cart)
4. Enter:
   - WhatsApp: +50912345678
   - Name: Test Buyer
   - Quantity: 1
5. **Expected:** Flash message "Piblisite ajoute nan panier!"

### Step 2: Buyer Submits Cart with Delivery Address
1. Go to `/shopping_card_update?whatsapp=+50912345678`
2. Enter delivery address: "123 Test Street, Port-au-Prince"
3. Check "Accept Terms" checkbox
4. Click "Soumèt Demann" (Submit Request)
5. **Expected:**
   - Flash message: "Demann ou a soumèt avèk siksè!"
   - Redirects to WhatsApp with message to seller
   - Delivery record created with status='pending'

### Step 3: Seller Sets Shipping Price
1. Seller clicks the link from WhatsApp
2. Opens `/seller_update_delivery/<delivery_id>`
3. **Expected to see:**
   - Buyer's WhatsApp number
   - Delivery address
   - List of cart items
   - Total product price
   - Form to enter shipping price
4. Enter shipping price: 50 Gkach
5. Click "Voye Pri Bay Achte a" (Send Price to Buyer)
6. **Expected:**
   - Flash message: "Pri livrezon mete ajou!"
   - Redirects to WhatsApp with message to buyer
   - Delivery status updated to 'price_set'

### Step 4: Buyer Confirms Purchase
1. Buyer clicks the link from WhatsApp
2. Opens `/buyer_confirm_delivery/<delivery_id>`
3. **Expected to see:**
   - Seller's WhatsApp number
   - Delivery address
   - List of cart items with prices
   - Price breakdown (products + shipping)
   - Total price
   - Confirm/Decline buttons
4. Click "Konfime Achte a" (Confirm Purchase)
5. **Expected:**
   - If sufficient balance: Flash message "Achte konfime avèk siksè!"
   - If insufficient balance: Redirects to `/achte_gkach`
   - Delivery status updated to 'confirmed'
   - Gkach deducted from buyer, credited to seller
   - Cart cleared

### Step 5: Buyer Declines Purchase
1. Follow steps 1-3 above
2. Click "Refize Achte a" (Decline Purchase)
3. **Expected:**
   - Flash message: "Ou te refize acha a. Panier ou vide."
   - Delivery status updated to 'declined'
   - Cart cleared
   - No payment processed

---

## Test Scenario 2: Direct WhatsApp Contact

### From Seller Page:
1. Go to `/seller_update_delivery/<delivery_id>`
2. Scroll to "Kontakte Achte a" section
3. Click WhatsApp button
4. **Expected:** Opens WhatsApp chat with buyer's number

### From Buyer Page:
1. Go to `/buyer_confirm_delivery/<delivery_id>`
2. Scroll to "Kontakte Vandè a" section
3. Click WhatsApp button
4. **Expected:** Opens WhatsApp chat with seller's number

---

## Test Scenario 3: Old Cart Flow (CartItem-based)

### Step 1: Buyer Adds Items
- Same as Scenario 1, Step 1

### Step 2: View Cart
1. Go to `/view_cart?whatsapp=+50912345678`
2. **Expected to see:**
   - List of cart items
   - Subtotals
   - Shipping status for each item

### Step 3: Seller Updates Cart (Old Flow)
1. Go to `/seller_update_cart/+50912345678`
2. Enter shipping fees for each item
3. Click "Renvoye Bay Achte" (Send to Buyer)
4. **Expected:**
   - Redirects to WhatsApp with message to buyer
   - CartItem records updated with shipping fees
   - negotiation_status set to 'seller_updated'

---

## Test Scenario 4: Admin Functions

### Login:
1. Go to `/admin/login`
2. Enter password from .env file
3. **Expected:** Redirects to admin dashboard

### Manage Ads:
1. View all submitted ads
2. Approve/reject ads
3. **Expected:** Status updates correctly

### Manage Gkach:
1. View all users with Gkach
2. Add/edit balance
3. Approve/reject Gkach requests
4. **Expected:** Balance updates correctly

---

## Test Scenario 5: Security Tests

### Environment Variables:
1. Check that SECRET_KEY is loaded from .env
2. Check that ADMIN_PASSWORD is loaded from .env
3. **Expected:** No hardcoded values in use

### File Upload:
1. Try uploading invalid file types
2. **Expected:** Proper error messages

### WhatsApp Number Formatting:
1. Try various formats: 12345678, 50912345678, +50912345678
2. **Expected:** All formatted to +509xxxxxxxx

---

## Common Issues & Solutions

### Issue: "Livrezon pa jwenn" (Delivery not found)
**Solution:** Check that delivery_id in URL is correct

### Issue: "Ou pa gen ase Gkach" (Insufficient Gkach)
**Solution:** 
1. Go to `/admin/manage_gkach`
2. Add Gkach balance to buyer's account

### Issue: WhatsApp link doesn't open
**Solution:** Ensure WhatsApp is installed or use web.whatsapp.com

### Issue: "Sesyon ekspire" (Session expired)
**Solution:** Start the flow again from the beginning

---

## Database Checks

### Check Delivery Records:
```python
from models import db, Delivery
deliveries = Delivery.query.all()
for d in deliveries:
    print(f"ID: {d.delivery_id}, Status: {d.status}, Buyer: {d.buyer_whatsapp}, Seller: {d.seller_whatsapp}")
```

### Check Cart Items:
```python
from models import db, CartItem, User
users = User.query.all()
for u in users:
    items = CartItem.query.filter_by(user_id=u.id).all()
    print(f"User: {u.whatsapp}, Items: {len(items)}")
```

### Check Gkach Balances:
```python
from models import db, UserGkach
users = UserGkach.query.all()
for u in users:
    print(f"User: {u.user_whatsapp}, Balance: {u.gkach_balance}")
```

---

## Performance Testing

### Load Test:
1. Add multiple items to cart
2. Submit cart
3. Check response time
4. **Expected:** < 2 seconds for most operations

### Concurrent Users:
1. Have multiple buyers submit carts simultaneously
2. **Expected:** No database conflicts or errors

---

## Browser Compatibility

Test on:
- [ ] Chrome/Edge (Desktop)
- [ ] Firefox (Desktop)
- [ ] Safari (Desktop)
- [ ] Chrome (Mobile)
- [ ] Safari (Mobile - iOS)

---

## Mobile Responsiveness

Test on mobile devices:
- [ ] Forms are easy to fill
- [ ] Buttons are clickable
- [ ] Text is readable
- [ ] Images display correctly
- [ ] WhatsApp links work

---

## Success Criteria

✅ Buyer can add items to cart
✅ Buyer can submit cart with delivery address
✅ Seller receives WhatsApp notification with link
✅ Seller can set shipping price
✅ Buyer receives WhatsApp notification with link
✅ Buyer can confirm purchase
✅ Buyer can decline purchase
✅ Payment processed correctly (Gkach deducted/credited)
✅ Cart cleared after purchase
✅ Direct WhatsApp contact works
✅ All messages in Haitian Creole
✅ No security vulnerabilities
✅ Environment variables work correctly

---

## Troubleshooting

### If seller link doesn't work:
1. Check that Delivery record exists
2. Check delivery.status is 'pending'
3. Check seller_whatsapp is correct

### If buyer link doesn't work:
1. Check that Delivery record exists
2. Check delivery.status is 'price_set'
3. Check buyer_whatsapp is correct

### If payment fails:
1. Check buyer has sufficient Gkach balance
2. Check UserGkach record exists for both buyer and seller
3. Check database transaction completed

---

## Automated Testing (Future)

Create test files for:
- `test_checkout_flow.py` - Test complete checkout process
- `test_whatsapp_formatting.py` - Test number formatting
- `test_security.py` - Test security features
- `test_api_routes.py` - Test API endpoints

---

## Monitoring

After deployment, monitor:
- Error logs for any exceptions
- Database for orphaned records
- User feedback on checkout process
- WhatsApp delivery rates

---

## Support

If issues persist:
1. Check application logs
2. Check database records
3. Verify environment variables are loaded
4. Test with different browsers
5. Clear browser cache and cookies
