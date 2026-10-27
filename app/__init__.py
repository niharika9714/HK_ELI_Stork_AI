import os
import secrets
from flask import Flask, jsonify
from .config import load_config
from .services.jobs import Jobs


def create_app(config=None):
    app = Flask(__name__)
    settings = config or load_config()
    secret = os.getenv(settings['app']['secret_env'])
    if settings['app']['mode'] == 'live' and not secret:
        raise ValueError('Live mode requires a persistent strong session secret.')
    app.secret_key = secret or secrets.token_hex(32)
    app.config.update(HKELI=settings, MAX_CONTENT_LENGTH=16384,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                      SESSION_COOKIE_SECURE=settings['app']['secure_cookie'])
    app.extensions['jobs'] = Jobs(settings['app']['job_workers'], settings['app']['max_jobs'], settings['app']['job_ttl_seconds'])
    from .controllers.api import bp
    app.register_blueprint(bp)

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        return response

    @app.errorhandler(PermissionError)
    def denied(error):
        return jsonify(error=str(error), code='access_denied'), 403

    @app.errorhandler(ValueError)
    def invalid(error):
        return jsonify(error=str(error), code='invalid_request'), 400

    return app
