# run.py
import os
from app import create_app

# Force Flask to use the correct current working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = create_app()

if __name__ == '__main__':
    print("=" * 60)
    print("Clarkson FAR Web Application Starting...")
    print(f"Current Directory: {os.getcwd()}")
    print(f"Template Folder  : {app.template_folder}")
    print(f"Static Folder    : {app.static_folder}")
    print("=" * 60)
    print("Access the app at: http://localhost:5000/login")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5000)