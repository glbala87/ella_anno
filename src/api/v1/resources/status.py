from flask import jsonify
from annotation.task import Task
from api.v1.resource import Resource


class StatusResource(Resource):
    def get(self, id=None):
        if id is None:
            return jsonify(Task.get_status_all())
        else:
            return jsonify(Task.get_status(str(id))[str(id)])
