import logging
import logging.config
import sys

def setup_logging():
    """Configures logging for the application."""
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(asctime)s %(name)s %(levelname)s %(message)s %(pathname)s %(lineno)d"
            },
        },
        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "stream": sys.stdout,
                "formatter": "json",
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["stdout"],
        },
    })

# Add python-json-logger to requirements.txt
# You might need to run: pip install python-json-logger
