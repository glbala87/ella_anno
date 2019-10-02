from api.v1.resource import Resource
from annotation.task import Task


class DeleteResource(Resource):
    def get(self, id):
        Task.delete(str(id))

        return "", 204
