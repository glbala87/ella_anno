from flask import jsonify, request
from api.v1.resource import Resource
from api.util.sample_utils import read_samples
from api.util.decorators import rest_filter


class ListSamplesResources(Resource):
    @rest_filter
    def get(self, rest_filter):
        samples = read_samples()
        if not rest_filter:
            rest_filter = {}
        keys = rest_filter.get("keys")
        name_filter = rest_filter.get("name")
        limit = int(request.args.get("limit", 0))

        if name_filter:
            samples = {
                k: v for k, v in samples.items() if name_filter.lower() in k.lower()
            }

        if keys:
            for k in samples:
                samples[k] = {
                    key: val for key, val in samples[k].items() if key in keys
                }

        if limit:
            sorted_samples = {}
            for k in sorted(samples.keys())[:limit]:
                sorted_samples[k] = samples[k]
            samples = sorted_samples

        return jsonify(samples)
