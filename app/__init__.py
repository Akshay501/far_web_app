# app/__init__.py
from flask import Flask
from flask_login import LoginManager
from .config import Config
from .utils import load_config
from .models import User

def create_app():
    app = Flask(__name__,
                template_folder='../templates',   # Force correct path
                static_folder='../static')

    app.config.from_object(Config)

    # Load DB config
    cfg = load_config()
    app.config['DB_CONFIG'] = cfg['db']

    # Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from .utils import get_db
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT * FROM users WHERE UserID = %s", (user_id,))
        data = cursor.fetchone()
        cursor.close()
        db.close()
        return User(data) if data else None

    # Register Blueprints
    from .routes import auth_bp, professor_bp, admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(professor_bp, url_prefix='/professor')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    return app