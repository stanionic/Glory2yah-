# Shopping Cart Flow Update - TODO

## Completed Tasks
- [x] Update shopping_cart route: After creating delivery, flash success message and redirect to achte page (instead of check_balance), so buyer waits for seller to set delivery cost.
- [x] Verify check_balance route calculates total_price = ad_price + delivery_cost and shows updated total.
- [x] Fix buy_ad route: deduct total_price from buyer balance, credit total_price to seller balance, and set delivery status to 'completed'.
- [x] Update notifications to include proper links for the flow.
- [x] Fix redirect after cart submission: redirect to seller's WhatsApp instead of achte page.

## Followup Steps
- [x] Test the complete flow: buyer submits cart → seller sets delivery cost → buyer receives notification → buyer checks balance and pays.
- [ ] Ensure WhatsApp notifications are working (currently showing connection errors in terminal output).
- [x] Verify that the buyer is redirected correctly after cart submission.
- [x] Confirm that the check_balance page displays the correct updated total after seller sets delivery cost.
