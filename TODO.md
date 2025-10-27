# Glory2YahPub Updates TODO

## 1. Icon Changes
- [x] Replace "+" with megaphone icon on "FÈ PIBLISITE W" buttons in all templates (index.html, batch.html, achte.html, base.html nav)
- [x] Replace "$" with "$" in circle icon for Gkach button in base.html nav

## 2. Responsive Design
- [x] Ensure all pages have proper responsive design with media queries
- [x] Make batch carousel fully responsive (adjust slide count, button sizes, etc.)
- [x] Test on mobile, tablet, desktop

## 3. Button Icons and Alignment
- [x] Add icons to all ad buttons (Achte, Kontak, FÈ PIBLISITE W)
- [x] Align the 3 buttons horizontally using flexbox (span mode)

## 4. Shopping Cart Flow
- [ ] Create new shopping cart template for delivery address and price setting
- [ ] Modify Achte button to redirect to shopping cart instead of check_balance
- [ ] Add route for shopping cart in app.py
- [ ] After setting delivery, redirect to check_balance
- [ ] Update models.py if needed for delivery info

## 5. WhatsApp Communication
- [x] Ensure all communication goes through WhatsApp (already implemented, verify)

## 6. Search Functionality in Achte
- [ ] Add search input for product name in achte.html
- [ ] Add image upload for image search
- [ ] Implement backend search logic in app.py
- [ ] Update achte route to handle search queries

## Testing
- [ ] Test all changes on different devices
- [ ] Verify button alignments and icons
- [ ] Test shopping cart flow end-to-end
- [ ] Test search functionality
