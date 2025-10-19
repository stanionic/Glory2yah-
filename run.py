from app import app
import os

if __name__ == '__main__':
    # Create uploads directory if it doesn't exist
    os.makedirs('static/uploads', exist_ok=True)
    
    print("Glory2yahPub starting...")
    print("Admin WhatsApp: +50942882076")
    print("Access at: http://localhost:5000")
    print("Admin panel: http://localhost:5000/admin")
    
    app.run(debug=True, host='0.0.0.0', port=5000)