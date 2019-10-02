from flask import send_file

from annotation.task import Task
from api.v1.resource import Resource


def raise_failed(id):
    failed = Task.is_failed(id)
    if failed:
        log = Task.get_log(id, failed_only=True)
        raise RuntimeError(log)


class ProcessResource(Resource):
    def get(self, id):
        id = str(id)
        Task.wait_for_task(id)
        raise_failed(id)
        result_file = Task.get_result(id)
        return send_file(result_file)
