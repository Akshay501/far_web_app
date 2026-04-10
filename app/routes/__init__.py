# app/routes/__init__.py
# This file makes the 'routes' directory a Python package
# and allows us to easily import all blueprints

from .auth import auth_bp
from .professor import professor_bp
from .admin import admin_bp

__all__ = ['auth_bp', 'professor_bp', 'admin_bp']