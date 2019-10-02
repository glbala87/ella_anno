from flask import make_response

from annotation.task import Task
from api.v1.resource import Resource


class DebugResource(Resource):
    def get(self, id):
        id = str(id)
        response = make_response(Task.get_log(id))
        response.headers["content-type"] = "text/plain"
        return response
