import os
import signal

from gevent import monkey
monkey.patch_all()  # noqa

from pyramid.config import Configurator

from gevent.pywsgi import WSGIServer, WSGIHandler

ENV_KEY = 'GI_CLOUD_'


def main():
    app = start_app()
    create_server(app)


def start_app(settings={}):
    """Update settings and create the WSGI app.

    The provided settings override the default and environment settings and are
    mainly used for testing purposes.
    """
    with Configurator() as config:
        apply_environ(config)
        config.add_settings(settings)
        configure(config)
        app = config.make_wsgi_app()
    return app


def create_server(app):
    """Create the main server script.
    """
    server = WSGIServer(
        ('0.0.0.0', 9090),
        app,
        handler_class=WSGIHandler,
    )
    # docker sends SIGTERM upon stop, let's gracefully shut down then
    signal.signal(signal.SIGTERM, lambda *_: server.stop(10000))
    server.serve_forever()


def apply_environ(config):
    """Apply application environment variables to the settings.
    """
    key_length = len(ENV_KEY)
    settings = {}
    for k, v in os.environ.items():
        if k.startswith(ENV_KEY):
            key = k[key_length:].lower().replace("_", ".")
            settings[key] = v
    config.add_settings(settings)


def configure(config):
    """Include and scan modules for Pyramid configuration."""
    config.include('.db')
    config.include('.static')
    config.include('lovely.ws.status.svcstatus')
    config.include('lovely.ws.status.probestatus')

    config.scan()
    config.scan('lovely.ws.status')
