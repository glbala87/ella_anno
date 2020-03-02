import os
import re

import logging

logger = logging.getLogger("anno")

# 13-32532632-A-G (het)
RE_GENOMIC = re.compile(
    "(?P<CHROM>\d+|MT|X|Y)-(?P<POS>\d+)-(?P<REF>[^-]+)-(?P<ALT>[^\s]+)(\s+\((?P<GT>.+)?\))?"
)
RE_VCF = re.compile("#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO")
# NM_3532523.2:c.2378A>T
RE_HGVSC = re.compile(".+:c\..+")

RE_SEQPILOT = re.compile(".*Transcript.*\tc. HGVS|.*c. HGVS.*\tTranscript")


def is_genomic(data):
    for l in data.split("\n"):
        if RE_GENOMIC.match(l) is None:
            return False, l
    return True, None


def is_seqpilot(data):
    header_line = None
    for l in data.split("\n"):
        if l and not header_line:
            header_line = l
            break

    return RE_SEQPILOT.match(l) is not None


def is_hgvsc(data):
    for l in data.split("\n"):
        if RE_HGVSC.match(l) is None:
            return False, l
    return True, None


def is_vcf(data):
    return RE_VCF.search(data) is not None


def genomic_to_vcf(data):
    header = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE"
    data_line = "{CHROM}\t{POS}\t.\t{REF}\t{ALT}\t.\tPASS\t.\t{FORMAT}\t{SAMPLE}"
    vcf_data = header
    gt_mapping = {"het": "0/1", "homo": "1/1", "hom": "1/1"}

    for l in data.split("\n"):
        m = RE_GENOMIC.match(l).groupdict()

        gt = m.pop("GT", None)
        m["FORMAT"] = "GT" if gt else "."
        m["SAMPLE"] = gt_mapping.get(gt, ".")
        vcf_data += "\n" + data_line.format(**m)
    return vcf_data


def _get_type_and_convert_data(data):
    data = data.strip()

    if is_vcf(data):
        return "vcf", data

    if is_seqpilot(data):
        return "hgvsc", data

    genomic, failing_line_genomic = is_genomic(data)
    if genomic:
        return "vcf", genomic_to_vcf(data)

    hgvsc, failing_line_hgvsc = is_hgvsc(data)
    if hgvsc:
        return "hgvsc", data

    if failing_line_hgvsc == failing_line_genomic:
        raise RuntimeError(
            "Unable to determine input type (vcf, seqpilot, genomic, or hgvsc). Not genomic or hgvsc: {}.".format(
                failing_line_genomic
            )
        )
    else:
        raise RuntimeError(
            "Unable to determine input type (vcf, seqpilot, genomic, or hgvsc). Not genomic: {}. Not hgvsc: {}.".format(
                failing_line_genomic, failing_line_hgvsc
            )
        )


def extract_data(data):
    type, data = _get_type_and_convert_data(data)
    if type == "vcf":
        # Replace spaces within columns, due to a VEP bug in VEP 79
        ptrn = re.compile("\n(?=[^#])", re.M)
        header, body = ptrn.split(data, 1)

        if "\t" in body:
            body = body.replace(" ", "--")

        vcf = "{}\n{}".format(header, body)
        hgvsc = None
    elif type == "hgvsc":
        vcf = None
        hgvsc = data

    return vcf, hgvsc


def str2bool(v):
    if isinstance(v, bool):
        return v
    else:
        return v.lower() in ("yes", "true", "t", "1")


def validate_target(target):
    if not target:
        return
    target_folder = os.environ.get("TARGETS")
    assert target_folder is not None, "TARGETS not specified in environment"
    assert os.path.isfile(os.path.join(target_folder, "targets", target))
