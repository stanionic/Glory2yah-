# TODO List for Adding /welcome Endpoint with Logging

## Information Gathered
- app.py is the main Flask application file.
- The app handles ad submissions, admin functions, and batch management.
- Uses SQLite for data storage.
- No existing logging setup.
- Need to add logging for request metadata (method, path).
- Add a new /welcome endpoint that returns JSON with welcome message.

## Plan
- Create src/logger.py for logging setup.
- Update app.py to import and initialize logger.
- Add /welcome route in app.py that logs request and returns JSON.

## Dependent Files to be edited
- app.py: Add import, logger setup, and new route.
- src/logger.py: New file for logging.

## Followup steps
- Run the app to test the new endpoint.
- Verify logging works.

## Steps
- [x] Create src/logger.py with logging configuration.
- [x] Update app.py to import logger and set it up.
- [x] Add /welcome route to app.py.
- [x] Test the endpoint by running the app and making a request.
