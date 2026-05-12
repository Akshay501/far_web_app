# app/__init__.py
from flask import Flask
from flask_login import LoginManager
from .config import Config
from .utils import load_config, close_db
from .models import User


def create_app():
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    app.config.from_object(Config)

    cfg = load_config()
    app.config['DB_CONFIG'] = cfg['db']
    app.config['DEPARTMENTS_ROOT'] = cfg.get('far', {}).get('departments_root', '')

    # Close DB connection cleanly after every request
    app.teardown_appcontext(close_db)

    # Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        from .utils import execute_query
        return User(execute_query(
            "SELECT * FROM users WHERE UserID = %s", (user_id,), fetchone=True
        ))

    # Register Blueprints
    from .routes import auth_bp, professor_bp, admin_bp
    from .routes.generate import generate_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(professor_bp, url_prefix='/professor')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(generate_bp)

    return app
