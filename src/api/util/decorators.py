from functools import wraps
from flask import request
import json


def parse_request(required, special):
    def wrapper(func):
        @wraps(func)
        def inner(*args, **kwargs):
            # Parse json
            data = {"variables": {}, "files": {}}
            json_data = request.get_json()
            if json_data:
                data["variables"] = json_data

            # Fetch files

            data["files"].update(
                {k: (v.filename, v.read()) for k, v in list(request.files.items())}
            )

            for k in request.form:
                data["variables"].update(
                    {k: json.loads(request.form[k].replace("'", '"'))}
                )

            # Strip required
            if not all(
                k in list(data["files"].keys()) + list(data["variables"].keys()) for k in required
            ):
                raise AssertionError(
                    "One or more required fields are missing: {}".format(required)
                )

            args = list(args)
            for k in required + special:
                if k in data["files"]:
                    args.append(data["files"].pop(k)[1])
                elif k in data["variables"]:
                    args.append(data["variables"].pop(k))
                else:
                    args.append(None)

            # Sort remaining into files or variables
            kwargs["data"] = data
            return func(*args, **kwargs)

        return inner

    return wrapper


def rest_filter(func):
    @wraps(func)
    def inner(*args, **kwargs):
        q_filter = None
        if request:
            q = request.args.get("q")
            # Replace with single with double quotes for the json loader
            if q:
                q = q.replace("'", '"')
                q_filter = json.loads(q)

        return func(*args, rest_filter=q_filter, **kwargs)

    return inner
