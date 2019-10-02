from api.v1.resource import Resource
from annotation.task import Task


class CancelResource(Resource):
    def get(self, id):
        Task.cancel(str(id))

        return "", 204
