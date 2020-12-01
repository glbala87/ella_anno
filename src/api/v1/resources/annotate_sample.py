import os
from flask import jsonify, make_response, request, send_file

from annotation.task import Task
from api.util.decorators import parse_request
from api.util.util import str2bool, validate_target
from api.util.sample_utils import read_samples
from api.v1.resource import Resource


class AnnotateSampleResource(Resource):
    @parse_request(["sample_id"], ["regions", "target", "targets"])
    def post(self, sample_id, regions, target, targets, data=None):
        # TODO: Remove 'targets'. Kept for now for backward compatibility.
        assert not (target and targets)
        if not target:
            target = targets
        validate_target(target)
        samples = read_samples()
        sample = samples[sample_id]

        for k, v in sample.items():
            path = os.path.join(os.environ["SAMPLES"], v)
            if os.path.isfile(path):
                data["variables"][k.upper()] = path
            else:
                data["variables"][k.upper()] = v

        data["variables"]["SAMPLE_ID"] = sample_id

        wait = str2bool(request.args.get("wait", False))

        vcf_file = os.path.join(os.environ["SAMPLES"], sample["vcf"])
        task_id, task_priority = Task.create_task(
            vcf=vcf_file, hgvsc=None, regions=regions, target=target, target_data=data
        )
        Task.queue(task_id, task_priority, wait=wait)
        if not wait:
            return make_response(jsonify({"task_id": task_id}), 202)
        else:
            return send_file(Task.get_result(task_id))
