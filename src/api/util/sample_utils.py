import os
import json


def read_samples():
    samples_json = os.path.join(os.environ["SAMPLES"], "samples.json")
    return json.load(open(samples_json, "r"))
