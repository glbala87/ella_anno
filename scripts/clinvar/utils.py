import os
import subprocess
import logging
import tempfile
import gzip


def vcf_validator(filename):
    try:
        subprocess.check_call("vcf-validator -d {}".format(filename), shell=True)
    except Exception as e:
        logging.error("vcf-validator failed ({})".format(filename))
        raise


def vcf_sort(filename):
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    try:
        subprocess.check_call("vcf-sort -c {} > {}".format(filename, tmp.name), shell=True)
        subprocess.check_call("mv {} {}".format(tmp.name, filename), shell=True)
    except:
        logging.error("vcf-sort failed ({})".format(filename))
        raise


def bgzip(filename):
    try:
        subprocess.check_call("bgzip -f {}".format(filename), shell=True)
    except Exception as e:
        logging.error("bgzip failed ({})".format(filename))
        raise


def tabix(filename):
    try:
        subprocess.check_call("tabix -p vcf {}".format(filename), shell=True)
    except Exception as e:
        logging.error("tabix failed ({})".format(filename))
        raise


def open_file(inputfile):
    """Opens input file. Downloads with wget if applicable. Opens with gzip og open based on extension"""
    if inputfile.startswith("ftp") or inputfile.startswith("http"):
        logging.info("Downloading input file {}".format(inputfile))
        download_to = os.path.split(inputfile)[-1]
        os.system("wget {} -O {}".format(inputfile, download_to))
        inputfile = download_to
        logging.info("Downloaded inputfile " + inputfile)

    if inputfile.endswith(".gz"):
        f = gzip.open(inputfile)
    else:
        f = open(inputfile)

    return f
