from flask import jsonify, make_response, request, send_file

from annotation.task import Task
from api.util.decorators import parse_request
from api.util.util import extract_data, str2bool
from api.v1.resource import Resource


class AnnotateResource(Resource):
    @parse_request(["input"], ["regions", "target", "targets"])
    def post(self, input, regions, target, targets, data=None):
        # TODO: Remove 'targets'. Kept for now for backward compatibility.
        assert not (target and targets)
        if not target:
            target = targets

        wait = str2bool(request.args.get("wait", False))

        # Create task object
        vcf, hgvsc = extract_data(input)

        task_id, task_priority = Task.create_task(
            vcf=vcf, hgvsc=hgvsc, regions=regions, target=target, target_data=data
        )
        Task.queue(task_id, task_priority, wait=wait)
        if not wait:
            return make_response(jsonify({"task_id": task_id}), 202)
        else:
            return send_file(Task.get_result(task_id))
