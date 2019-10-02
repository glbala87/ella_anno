import os
import shutil
from api.v1.resource import Resource
from config import config
from annotation.task import Task


def remove_files():
    for d in os.listdir(config["work_folder"]):
        shutil.rmtree(os.path.join(config["work_folder"], d))


class ResetResource(Resource):
    def get(self):
        for id in Task.get_active_task_ids():
            Task.cancel(id)

        remove_files()

        return "", 204
