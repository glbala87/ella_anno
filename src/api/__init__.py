import os
from flask import Flask
from multiprocessing import cpu_count
from multiprocessing.pool import ThreadPool
import logging
from annotation.task import Task

logger = logging.getLogger("anno")
app = Flask(__name__)

WORKERPOOL = {
    "NORMAL": ThreadPool(processes=int(os.environ.get('WORKERS', 1))),
    "PRIORITY": ThreadPool(processes=1),
}
logger.info(
    "Initiated WORKERPOOL['NORMAL'] with %d threads."
    % (WORKERPOOL["NORMAL"]._processes)
)
logger.info(
    "Initiated WORKERPOOL['PRIORITY'] with %d threads."
    % (WORKERPOOL["PRIORITY"]._processes)
)


def restart_active_tasks():
    all_tasks = Task.get_status_all(full=True)
    active_tasks = [k for k, v in list(all_tasks.items()) if v["active"]]
    for id in sorted(active_tasks):
        Task.restart(id)


restart_active_tasks()


class ApiError(RuntimeError):
    pass
