import os
import sys
import logging
import time
from flask import jsonify

from flask_restful import Api
from api import app
from api.v1 import ApiV1

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Set up anno logger
loglevel = logging.INFO

logger = logging.getLogger("anno")
logger.setLevel(loglevel)

# create a file handler
handler = logging.StreamHandler()
handler.setLevel(loglevel)

# create a logging format
formatter = logging.Formatter("%(asctime)s\t%(pathname)s:%(lineno)d - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

# add the handlers to the logger
logger.addHandler(handler)


class ApiErrorHandling(Api):
    def handle_error(self, e):
        code = e.code if hasattr(e, "code") else 500
        msg = str(code) + " " + e.__class__.__name__ + ": "
        if hasattr(e, "message") and e.message:
            msg += e.message
        elif hasattr(e, "description") and e.description:
            msg += e.description
        else:
            msg += "Unknown error"
        import traceback

        traceback.print_exc()

        return jsonify({"message": msg}), code


api = ApiErrorHandling(app, catch_all_404s=True)


# Setup resources for v1
ApiV1(app, api).setup_api()

if __name__ == "__main__":
    opts = {}
    opts["host"] = "0.0.0.0"
    opts["threaded"] = True
    opts["port"] = int(os.getenv("API_PORT", "6000"))

    if os.environ.get("DEBUG"):
        opts["use_reloader"] = True
        opts["reloader_interval"] = 3
        opts["debug"] = True

    app.run(**opts)
