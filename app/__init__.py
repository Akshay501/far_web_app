# app/__init__.py
import logging
from flask import Flask, render_template
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

    # Phase 5 — path to Departments/ folder
    far_cfg = cfg.get('far', {})
    app.config['DEPARTMENTS_ROOT'] = far_cfg.get('departments_root', '')

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

    # ── Custom error handlers ──────────────────────────────────────────────
    # These replace Flask's default plain-white error pages with our
    # branded Clarkson pages. The number after @app.errorhandler is the
    # HTTP status code that triggers this handler.

    @app.errorhandler(404)
    def page_not_found(e):
        """
        Runs when someone visits a URL that doesn't exist.
        e.g. /professor/nonexistent or a typo in the URL bar.
        We log it at INFO level (not an emergency, just a wrong URL).
        """
        app.logger.info(f'404 - Page not found: {e}')
        return render_template('404.html'), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        """
        Runs when someone sends the wrong HTTP method to a route.
        e.g. sending a POST to a GET-only route.
        We redirect to 404 page since from the user's perspective
        the page 'doesn't exist' for their request.
        """
        app.logger.warning(f'405 - Method not allowed: {e}')
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(e):
        """
        Runs when an unhandled Python exception occurs anywhere in the app.
        This is serious — we log it at ERROR level so it can be investigated.
        We also rollback any pending DB transaction to avoid data corruption.
        """
        app.logger.error(f'500 - Internal server error: {e}', exc_info=True)
        # Close the DB connection in case it's in a bad state
        close_db()
        return render_template('500.html'), 500

    @app.errorhandler(403)
    def forbidden(e):
        """
        Runs when a user tries to access something they're not allowed to.
        e.g. a professor trying to access admin pages.
        """
        app.logger.warning(f'403 - Forbidden: {e}')
        return render_template('404.html'), 403

    # ── Logging setup ──────────────────────────────────────────────────────
    # Set up logging so errors are written to a file in production
    # In debug mode Flask already logs to console, so we only add
    # file logging when NOT in debug mode.
    if not app.debug:
        file_handler = logging.FileHandler('far_app.log')
        file_handler.setLevel(logging.WARNING)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.WARNING)

    return app
