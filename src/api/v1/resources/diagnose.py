import os
import subprocess

from flask import make_response

from annotation.task import Task
from api.v1.resource import Resource
from config import config


def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, "Yi", suffix)


def get_size(top, exclude=None):
    if exclude is None:
        exclude = []
    size = 0
    for dirname, subdir, files in os.walk(top):
        if dirname in exclude:
            continue
        for f in files:
            filepath = os.path.join(dirname, f)
            if not os.path.islink(filepath):
                size += os.path.getsize(filepath)

    return size


def check_output(cmd, on_error="N/A"):
    try:
        return subprocess.check_output(cmd, shell=True).decode("utf-8")
    except subprocess.CalledProcessError:
        return on_error


class DiagnoseResource(Resource):
    def get(self):
        all_task_ids = list(Task.get_status_all().keys())
        total = len(all_task_ids)
        finalized = 0
        failed = 0
        active = 0

        for id in all_task_ids:
            if Task.is_finished(id):
                finalized += 1
                if Task.is_failed(id):
                    failed += 1
            else:
                active += 1

        res = "TASKS\n"
        res += "\tTotal: " + str(total) + "\n"
        res += "\tFinalized: " + str(finalized) + "\n"
        res += "\tFailed: " + str(failed) + "\n"
        res += "\tActive: " + str(active) + "\n"

        uta = "UTA " + os.environ["UTA_DB_URL"]
        seqrepo = "SEQREPO " + os.environ["HGVS_SEQREPO_DIR"]

        bedtools = check_output("bedtools --version")
        bedtools += " ({})".format(check_output("which bedtools"))

        vt = check_output("vt --version 2>&1 | grep vt")
        vt += " ({})".format(check_output("which vt"))

        tabix = check_output("tabix -v 2>&1 | grep Version || :")
        tabix += " ({})".format(check_output("which tabix"))

        bgzip = " ({})".format(check_output("which bgzip"))

        vcfanno = check_output("vcfanno 2>&1 | grep version")
        vcfanno += " ({})".format(check_output("which vcfanno"))

        vcftools = check_output("vcftools --version")
        vcftools += " ({})".format(check_output("which vcftools"))

        vcfvalidator = "vcf-validator: See vcftools"
        vcfvalidator += " ({})".format(check_output("which vcf-validator"))

        python = check_output("python3 --version 2>&1")
        python += " ({})".format(check_output("which python3"))

        perl = check_output("perl --version | perl --version | grep -oP 'This is \K.*'")
        perl += " ({})".format(check_output("which perl"))

        # vep = subprocess.check_output("vep | grep ' ensembl'", shell=True) # For vep versions >87?
        vep = check_output("vep | grep 'version'")
        vep += " ({})".format(check_output("which vep"))

        res += "\nTOOLS\n"
        res += "\t%s\n" % uta
        res += "\t%s\n" % seqrepo
        res += "\n"

        res += "\t{}\n".format(bedtools.replace("\n", ""))
        res += "\t{}\n".format(vt.replace("\n", ""))
        res += "\t{}\n".format(vcfanno.replace("\n", ""))
        res += "\tVEP {}\n".format(vep.replace("\n", ""))
        res += "\t{}\n".format(vcftools.replace("\n", ""))
        res += "\t{}\n".format(vcfvalidator.replace("\n", ""))

        res += "\tTabix {}\n".format(tabix.replace("\n", ""))
        res += "\tbgzip {}\n".format(bgzip.replace("\n", ""))

        res += "\t{}\n".format(python.replace("\n", ""))
        res += "\t{}\n".format(perl.replace("\n", ""))
        res += "\n"

        res += "\tPATH {}\n".format(os.environ.get("PATH", "N/A"))
        res += "\tPERL5LIB {}\n".format(os.environ.get("PERL5LIB", "N/A"))

        res += "\nENVIRONMENT\n"
        N = max(len(k) for k in os.environ.keys())
        for k in sorted(os.environ):
            res += "\t{:<{width}}\t{}\n".format(k, os.environ[k], width=N + 5)

        res += (
            "\nDisk space used: " + sizeof_fmt(get_size(config["work_folder"])) + "\n"
        )

        response = make_response(res)
        response.headers["content-type"] = "text/plain"
        return response
