# app/__init__.py
import logging
import os
from flask import Flask, render_template
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from .config import Config
from .utils import load_config, close_db
from .models import User


def create_app():
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    app.config.from_object(Config)

    # Initialize CSRF protection globally
    # This makes csrf_token() available in all Jinja2 templates
    csrf = CSRFProtect(app)

    # Exempt the standalone blueprint — no login required, uses its own session
    from .routes.standalone import standalone_bp as _standalone_bp
    csrf.exempt(_standalone_bp)

    cfg = load_config()
    # Phase 2: secrets prefer the environment (.env via load_dotenv in
    # app.config). config.yml stays the fallback so existing setups
    # keep working until their .env exists.
    env_pw = os.getenv('FAR_DB_PASSWORD')
    if env_pw:
        cfg['db']['pw'] = env_pw
    app.config['DB_CONFIG'] = cfg['db']
    app.config['SCOPUS_API_KEY'] = os.getenv('FAR_SCOPUS_API_KEY')
    if app.config['SECRET_KEY'] == 'clarkson-far-2026-secret-key':
        app.logger.warning(
            'SECRET_KEY is the committed default - sessions are '
            'forgeable. Set SECRET_KEY in .env before any deployment.')

    # Flat professors root — folders are named by ProfessorKey
    far_cfg = cfg.get('far', {})
    app.config['PROFESSORS_ROOT'] = far_cfg.get('professors_root', '')
    # Server-side scaffold template (source for new professor folders)
    app.config['SCAFFOLD_TEMPLATE'] = far_cfg.get('scaffold_template', '')
    # Institution details + department list (registration/profile)
    app.config['INSTITUTION'] = far_cfg.get('institution', {})
    app.config['DEPARTMENTS'] = far_cfg.get('departments', [])

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
    from .routes.standalone import standalone_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(professor_bp, url_prefix='/professor')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(generate_bp)
    app.register_blueprint(standalone_bp)

    # Add enumerate filter to Jinja2
    # WHY: Jinja2 doesn't have enumerate() built-in like Python.
    # We use it in standalone templates to get the row index for
    # edit/delete operations: {% for i, row in rows|enumerate %}
    app.jinja_env.filters['enumerate'] = enumerate

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
