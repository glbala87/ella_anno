import errno
import glob
import logging
import os
import shutil
import subprocess
import time
from collections import OrderedDict
from functools import wraps

import psutil
from config import config
from command import Command
from api.util.util import validate_target


logger = logging.getLogger("anno")


def check_task(provide_task_dir=False):
    def _check_task(func):
        @wraps(func)
        def inner(*args, **kwargs):
            id = args[0]
            task_dir = os.path.join(config["work_folder"], id)
            if provide_task_dir:
                kwargs["task_dir"] = task_dir

            assert os.path.isdir(task_dir), "Task with id {} does not exist".format(id)
            return func(*args, **kwargs)

        return inner

    return _check_task


def _kill_recursive(pid):
    """Recursively kill processes, starting from descendants"""
    try:
        p = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    for c in p.children():
        _kill_recursive(c.pid)
    try:
        os.kill(pid, 9)
    except (OSError, psutil.NoSuchProcess):
        pass


# https://stackoverflow.com/questions/600268
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def generate_id():
    id = str(int(time.time() * 1e6))
    return id


class Task(object):
    @staticmethod
    def write_target_files(work_dir, target_data):
        target_files = dict()
        for k, (filename, content) in target_data["files"].iteritems():
            filename = os.path.join(work_dir, filename)
            with open(filename, "w") as f:
                f.write(content)
            target_files[k] = filename

        target_env = dict()
        for k, v in target_files.iteritems():
            target_env[k.split(".")[0]] = v

        return target_env

    @staticmethod
    def create_task(
        vcf=None,
        hgvsc=None,
        regions=None,
        target=None,
        target_data=None,
        convert_only=False,
    ):
        task_id = generate_id()
        task_dir = os.path.join(config["work_folder"], str(task_id))
        assert not os.path.isdir(task_dir)
        mkdir_p(task_dir)

        priority = False
        target_env = dict(target_data["variables"])
        target_env.update(Task.write_target_files(task_dir, target_data))

        validate_target(target)

        input_regions = None
        if regions is not None:
            input_regions = os.path.join(task_dir, "regions.bed")

            with open(input_regions, "w") as f:
                f.write(regions)

        if vcf:
            input_vcf = os.path.join(task_dir, "input.vcf")
            if os.path.isfile(vcf):
                os.symlink(vcf, input_vcf)
                line_count = int(
                    subprocess.check_output(
                        "wc -l {} | cut -d' ' -f1".format(vcf), shell=True
                    )
                )
                priority = line_count < 1000
            else:
                with open(input_vcf, "w") as f:
                    f.write(vcf)
                priority = vcf.count("\n") < 1000

            Command.create_from_vcf(
                task_dir,
                input_vcf,
                input_regions=input_regions,
                convert_only=convert_only,
                target=target,
                target_env=target_env,
            )

        elif hgvsc:

            input_hgvsc = os.path.join(task_dir, "input.txt")
            with open(input_hgvsc, "w") as f:
                f.write(hgvsc)
            priority = hgvsc.count("\n") < 100

            Command.create_from_hgvsc(
                task_dir,
                input_hgvsc,
                input_regions=input_regions,
                convert_only=convert_only,
                target=target,
                target_env=target_env,
            )
        else:
            raise RuntimeError("Missing data for argument vcf or hgvsc")

        return task_id, priority

    @staticmethod
    @check_task(provide_task_dir=True)
    def run(id, task_dir=None):
        if not Task.is_finished(id):
            p = subprocess.Popen(
                ["bash", os.path.join(task_dir, "cmd.sh")],
                stdout=None if config["verbose"] else open("/dev/null", "a"),
            )
            with open(os.path.join(task_dir, "PID"), "w") as f:
                f.write(str(p.pid))

            p.wait()
            os.unlink(os.path.join(task_dir, "PID"))
            # A negative value indicates that the process was killed by a signal.
            # If this is because the api was stopped, then the task should be restarted.
            # This is handled in src/api/__init__.py
            # If this is because the specific task was cancelled, then the ACTIVE-file is unlinked in Task.cancel
            if p.returncode < 0:
                return

            os.unlink(os.path.join(task_dir, "ACTIVE"))
            if p.returncode == 0:
                subprocess.call(
                    "touch {}".format(os.path.join(task_dir, "SUCCESS")), shell=True
                )
            else:
                subprocess.call(
                    "touch {}".format(os.path.join(task_dir, "FAILED")), shell=True
                )

    @staticmethod
    def get_all_task_ids():
        pattern = config["work_folder"] + "/[0-9]*"
        ids = []
        for folder in glob.iglob(pattern):
            if not os.path.isdir(folder):
                continue
            id = os.path.split(folder)[1]
            ids.append(id)
        return ids

    @staticmethod
    def get_active_task_ids():
        return [id for id in Task.get_all_task_ids() if not Task.is_finished(id)]

    @staticmethod
    def get_failed_task_ids():
        return [id for id in Task.get_all_task_ids() if Task.is_failed(id)]

    @staticmethod
    def get_successful_task_ids():
        return [id for id in Task.get_all_task_ids() if Task.is_successful(id)]

    @staticmethod
    @check_task(provide_task_dir=True)
    def queue(id, priority, wait=False, task_dir=None):
        subprocess.call("touch {}/ACTIVE".format(task_dir), shell=True)
        ts = subprocess.check_output("date '+%Y-%m-%d %H:%M:%S.%N'", shell=True)
        status_file = os.path.join(task_dir, "STATUS")
        with open(status_file, "w") as f:
            f.write("\t".join([ts.strip(), "QUEUED", ""]) + "\n")
        from api import WORKERPOOL

        if not priority:
            logger.info("NO PRIORITY: NORMAL QUEUE (id={})".format(id))
            worker = WORKERPOOL["NORMAL"].apply_async(Task.run, (id,))
        else:
            if len(WORKERPOOL["NORMAL"]._cache) < WORKERPOOL["NORMAL"]._processes:
                logger.info("PRIORITY: NORMAL QUEUE (id={})".format(id))
                worker = WORKERPOOL["NORMAL"].apply_async(Task.run, (id,))
            else:
                logger.info("PRIORITY: PRIORITY QUEUE (id={})".format(id))
                worker = WORKERPOOL["PRIORITY"].apply_async(Task.run, (id,))

        if wait:
            worker.get()

    @staticmethod
    @check_task(provide_task_dir=True)
    def get_status(id, full=True, task_dir=None):
        status_file = os.path.join(task_dir, "STATUS")
        if not os.path.isfile(status_file):
            return {}
        else:
            if not full:
                status = subprocess.check_output(["tail", "-1", status_file]).strip()
                status = " ".join(status.split("\t")[1:])
                return {id: status}
            else:
                d = OrderedDict()
                with open(status_file, "r") as s:
                    for l in s:
                        vals = l.strip().split("\t")
                        k, v = vals[0], " ".join(vals[1:])
                        d[k] = v
                return {
                    id: {
                        "status": d,
                        "active": not Task.is_finished(id),
                        "error": Task.is_failed(id),
                    }
                }
        return {}

    @staticmethod
    def get_status_all(full=False):
        status = dict()
        for id in Task.get_all_task_ids():
            status.update(Task.get_status(id, full=full))
        return status

    @staticmethod
    @check_task(provide_task_dir=True)
    def get_result(id, task_dir=None):
        return os.path.join(task_dir, "output.vcf")

    @staticmethod
    @check_task()
    def is_finished(id):
        return Task.is_failed(id) or Task.is_successful(id)

    @staticmethod
    @check_task(provide_task_dir=True)
    def is_failed(id, task_dir=None):
        failed_file = os.path.join(task_dir, "FAILED")
        return os.path.isfile(failed_file)

    @staticmethod
    @check_task(provide_task_dir=True)
    def is_successful(id, task_dir=None):
        success_file = os.path.join(task_dir, "SUCCESS")
        return os.path.isfile(success_file)

    @staticmethod
    @check_task(provide_task_dir=True)
    def get_log(id, failed_only=False, task_dir=None):
        status_file = os.path.join(task_dir, "STATUS")
        modes = ["FAILED"]
        if not failed_only:
            modes.append("DONE")
        log = ""
        with open(status_file, "r") as f:
            for l in f:
                step, mode = [v.strip() for v in l.split("\t")[1:]]

                if mode in modes:
                    log_file = os.path.join(task_dir, step, "output.log")
                    log += "## {}: {} ##\n".format(step, mode)
                    with open(log_file, "r") as lf:
                        log += lf.read() + "\n"
        return log

    @staticmethod
    @check_task()
    def wait_for_task(id):
        logger.info("Waiting for task to finish (task_id=%s)" % id)
        n = 0
        while not Task.is_finished(id):
            time.sleep(0.5)
            n += 1
            if n % 200 == 0:
                logger.warning(
                    "Task with id {} appears to be taking longer than expected...".format(
                        id
                    )
                )

    @staticmethod
    @check_task(provide_task_dir=True)
    def cancel(id, task_dir=None):
        assert not Task.is_finished(id), "Task {} is already finished".format(id)
        logger.info("Cancelling task {}".format(id))
        pid_file = os.path.join(task_dir, "PID")
        status_file = os.path.join(task_dir, "STATUS")

        if os.path.isfile(pid_file):
            with open(pid_file, "r") as f:
                pid = f.read().strip()
            _kill_recursive(int(pid))
            os.unlink(pid_file)

        try:
            os.unlink(os.path.join(task_dir, "ACTIVE"))
        except OSError:
            pass

        subprocess.call("touch {}".format(os.path.join(task_dir, "FAILED")), shell=True)
        assert Task.is_finished(id), "Task {} not finished correctly".format(id)

        ts = subprocess.check_output("date '+%Y-%m-%d %H:%M:%S.%N'", shell=True)
        with open(status_file, "a") as f:
            f.write("\t".join([ts.strip(), "CANCELLED", ""]) + "\n")

    @staticmethod
    @check_task(provide_task_dir=True)
    def delete(id, task_dir=None):
        if not Task.is_finished(id):
            Task.cancel(id)

        shutil.rmtree(task_dir)

    @staticmethod
    @check_task(provide_task_dir=True)
    def restart(id, priority=False, task_dir=None):
        logger.info("Restarting task {}".format(id))
        # Remove files generated by interrupted or finished task
        if not Task.is_finished(id):
            Task.cancel(id)

        for f in os.listdir(task_dir):
            if os.path.isdir(os.path.join(task_dir, f)):
                shutil.rmtree(os.path.join(task_dir, f))

        for f in ["STATUS", "SUCCESS", "FAILED", "output.vcf"]:
            if os.path.isfile(os.path.join(task_dir, f)):
                os.unlink(os.path.join(os.path.join(task_dir, f)))

        Task.queue(id, priority)
