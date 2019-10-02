from flask import jsonify

from api.v1.resource import Resource
from config import config


class ConfigResource(Resource):
    def get(self):
        return jsonify(config)
