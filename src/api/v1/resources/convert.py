from flask import jsonify, make_response, request, send_file

from annotation.task import Task
from api.util.decorators import parse_request
from api.util.util import extract_data, str2bool
from api.v1.resource import Resource


class ConvertResource(Resource):
    @parse_request(["input"], ["regions"])
    def post(self, input, regions, data=None):

        wait = str2bool(request.args.get("wait", False))

        # Create task object
        vcf, hgvsc = extract_data(input)

        task_id, task_priority = Task.create_task(
            vcf=vcf,
            hgvsc=hgvsc,
            regions=regions,
            target_data=data,
            convert_only=True
        )
        Task.queue(task_id, task_priority, wait=wait)
        if not wait:
            return make_response(jsonify({"task_id": task_id}), 202)
        else:
            return send_file(Task.get_result(task_id))
