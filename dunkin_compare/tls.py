"""Use Python's configured trust plus certifi's maintained public CA roots."""
import ssl

import certifi


def verified_context():
    context=ssl.create_default_context()
    context.load_verify_locations(cafile=certifi.where())
    return context
