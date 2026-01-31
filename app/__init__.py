"""
CampusIQ - Flask Application Factory
Production-ready multi-tenant college management system
"""
import os
import logging
from datetime import timedelta
from flask import Flask, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from .config import config


def create_app(config_name=None):
    """Application factory pattern"""
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'development')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Initialize extensions
    _init_extensions(app)
    
    # Register blueprints
    _register_blueprints(app)
    
    # Register error handlers
    _register_error_handlers(app)
    
    # Setup logging
    _setup_logging(app)
    
    return app


def _init_extensions(app):
    """Initialize Flask extensions"""
    # CORS - Allow web frontend
    CORS(app, resources={
        r"/api/*": {
            "origins": app.config.get('CORS_ORIGINS', ['http://localhost:3000']),
            "methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Tenant-ID"],
            "supports_credentials": True
        }
    })
    

    # Database
    from flask_sqlalchemy import SQLAlchemy
    db = SQLAlchemy()
    db.init_app(app)
    
    # Rate Limiting
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=["100 per minute", "1000 per hour"],
        storage_uri=app.config.get('REDIS_URL', 'memory://')
    )
    app.limiter = limiter


def _register_blueprints(app):
    """Register all API blueprints"""
    from .routes.auth import auth_bp
    from .routes.schedules import schedules_bp
    from .routes.qna import qna_bp
    from .routes.blueprints import (
        colleges_bp, users_bp, faculty_bp, 
        results_bp, admin_bp, dashboard_bp
    )
    # Role-specific routes
    from .routes.super_admin import super_admin_bp
    from .routes.college_admin import college_admin_bp
    from .routes.staff import staff_bp
    
    # API routes
    app.register_blueprint(auth_bp, url_prefix='/api/v1/auth')
    app.register_blueprint(colleges_bp, url_prefix='/api/v1/colleges')
    app.register_blueprint(users_bp, url_prefix='/api/v1/users')
    app.register_blueprint(faculty_bp, url_prefix='/api/v1/faculty')
    app.register_blueprint(schedules_bp, url_prefix='/api/v1/schedules')
    app.register_blueprint(results_bp, url_prefix='/api/v1/results')
    app.register_blueprint(qna_bp, url_prefix='/api/v1/qna')
    app.register_blueprint(admin_bp, url_prefix='/api/v1/admin')
    app.register_blueprint(dashboard_bp, url_prefix='/api/v1/dashboard')
    
    # Role-specific API routes (new)
    app.register_blueprint(super_admin_bp)     # /api/v1/super-admin/*
    app.register_blueprint(college_admin_bp)   # /api/v1/college-admin/*
    app.register_blueprint(staff_bp)           # /api/v1/staff/*
    
    # Health check
    @app.route('/health')
    def health_check():
        return jsonify({
            'status': 'healthy',
            'app': 'CampusIQ',
            'version': '1.0.0'
        })

    # Root route
    @app.route('/')
    def index():
        return jsonify({
            'message': 'Welcome to CampusIQ API',
            'docs': '/api/docs',
            'health': '/health'
        })


def _register_error_handlers(app):
    """Register global error handlers"""
    from .utils.exceptions import (
        CampusIQException,
        UnauthorizedException,
        ForbiddenException,
        NotFoundException,
        ValidationException,
        TenantAccessException
    )
    
    @app.errorhandler(CampusIQException)
    def handle_campusiq_exception(error):
        return jsonify({
            'success': False,
            'error': True,
            'code': error.code,
            'message': error.message,
            'details': error.details
        }), error.status_code
    
    @app.errorhandler(UnauthorizedException)
    def handle_unauthorized(error):
        return jsonify({
            'success': False,
            'error': True,
            'code': 'UNAUTHORIZED',
            'message': str(error)
        }), 401
    
    @app.errorhandler(ForbiddenException)
    def handle_forbidden(error):
        return jsonify({
            'success': False,
            'error': True,
            'code': 'FORBIDDEN',
            'message': str(error)
        }), 403
    
    @app.errorhandler(NotFoundException)
    def handle_not_found(error):
        return jsonify({
            'success': False,
            'error': True,
            'code': 'NOT_FOUND',
            'message': str(error)
        }), 404
    
    @app.errorhandler(ValidationException)
    def handle_validation(error):
        return jsonify({
            'success': False,
            'error': True,
            'code': 'VALIDATION_ERROR',
            'message': str(error),
            'fields': getattr(error, 'fields', {})
        }), 400
    
    @app.errorhandler(TenantAccessException)
    def handle_tenant_access(error):
        return jsonify({
            'success': False,
            'error': True,
            'code': 'TENANT_ACCESS_DENIED',
            'message': 'You do not have access to this college\'s data'
        }), 403
    
    @app.errorhandler(404)
    def handle_404(error):
        return jsonify({
            'success': False,
            'error': True,
            'code': 'ENDPOINT_NOT_FOUND',
            'message': 'The requested endpoint does not exist'
        }), 404
    
    @app.errorhandler(500)
    def handle_500(error):
        import traceback
        app.logger.error(f'Internal server error: {error}')
        app.logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': True,
            'code': 'INTERNAL_ERROR',
            'message': 'An internal server error occurred',
            'details': str(error) if app.debug else None
        }), 500


def _setup_logging(app):
    """Configure application logging"""
    if not app.debug:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
        )
        handler.setFormatter(formatter)
        app.logger.addHandler(handler)
        app.logger.setLevel(logging.INFO)
