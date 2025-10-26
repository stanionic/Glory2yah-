# TODO: Update Glory2YahPub App for Terms Acceptance in Upload Forms

## Tasks
- [ ] Add terms acceptance checkbox to templates/upload_payment.html
- [ ] Add terms acceptance checkbox to templates/upload_gkach_approval.html
- [ ] Update app.py route for upload_payment to check request.form.get('accept_terms')
- [ ] Update app.py route for upload_gkach_approval to check request.form.get('accept_terms')
- [ ] Add flash error if terms not accepted in both routes
- [ ] Test the app by running it to verify changes
