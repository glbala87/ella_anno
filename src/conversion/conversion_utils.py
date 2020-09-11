import signal

from . import vcfhelper

RESEQ_ACCESSION = {
    "hg19": {
        "1": "NC_000001.10",
        "2": "NC_000002.11",
        "3": "NC_000003.11",
        "4": "NC_000004.11",
        "5": "NC_000005.9",
        "6": "NC_000006.11",
        "7": "NC_000007.13",
        "8": "NC_000008.10",
        "9": "NC_000009.11",
        "10": "NC_000010.10",
        "11": "NC_000011.9",
        "12": "NC_000012.11",
        "13": "NC_000013.10",
        "14": "NC_000014.8",
        "15": "NC_000015.9",
        "16": "NC_000016.9",
        "17": "NC_000017.10",
        "18": "NC_000018.9",
        "19": "NC_000019.9",
        "20": "NC_000020.10",
        "21": "NC_000021.8",
        "22": "NC_000022.10",
        "X": "NC_000023.10",
        "Y": "NC_000024.9",
    },
    "hg38": {
        "1": "NC_000001.11",
        "2": "NC_000002.12",
        "3": "NC_000003.12",
        "4": "NC_000004.12",
        "5": "NC_000005.10",
        "6": "NC_000006.12",
        "7": "NC_000007.14",
        "8": "NC_000008.11",
        "9": "NC_000009.12",
        "10": "NC_000010.11",
        "11": "NC_000011.10",
        "12": "NC_000012.12",
        "13": "NC_000013.11",
        "14": "NC_000014.9",
        "15": "NC_000015.10",
        "16": "NC_000016.10",
        "17": "NC_000017.11",
        "18": "NC_000018.10",
        "19": "NC_000019.10",
        "20": "NC_000020.11",
        "21": "NC_000021.9",
        "22": "NC_000022.11",
        "X": "NC_000023.101",
        "Y": "NC_000024.10",
    },
}


def get_chr(accession):
    """
    Fetches chromosome from reference accession.
    """
    return next(k for k, v in RESEQ_ACCESSION["hg19"].items() if v == accession)


def get_alt_for_inversion(ref):
    translation_table = str.maketrans("ACGT", "TGCA")
    return "".join(reversed(ref.translate(translation_table)))


def var_g_to_vcf(var_g, fasta):
    """
    Convert var_g to vcf using the genome reference to add bases where needed.
    """
    chrom = get_chr(var_g.ac)
    ref = var_g.posedit.edit.ref
    alt = getattr(var_g.posedit.edit, "alt", None)
    start = var_g.posedit.pos.start.base
    end = var_g.posedit.pos.end.base

    variant_type = var_g.posedit.edit.type

    vcf_data = {"chr": chrom}
    if variant_type == "sub" or variant_type == "identity":  # snp
        assert alt is not None
        vcf_data.update({"pos": start, "ref": ref, "alt": alt})
    elif variant_type == "inv":
        assert alt is None
        alt = get_alt_for_inversion(ref)
        vcf_data.update({"pos": start, "ref": ref, "alt": alt})
    elif variant_type == "dup":
        _, vcf_pos, _, ref, alt = vcfhelper.VCFAlleleCreator(fasta).duplication(chrom, start - 1, end, duplicated=ref)
        vcf_data.update({"pos": vcf_pos, "ref": ref, "alt": alt})
    elif variant_type == "del":
        _, vcf_pos, _, ref, alt = vcfhelper.VCFAlleleCreator(fasta).deletion(chrom, start - 1, end, deleted=ref)
        vcf_data.update({"pos": vcf_pos, "ref": ref, "alt": alt})
    elif variant_type == "ins":
        _, vcf_pos, _, ref, alt = vcfhelper.VCFAlleleCreator(fasta).insertion(chrom, start - 1, alt)
        vcf_data.update({"pos": vcf_pos, "ref": ref, "alt": alt})
    elif variant_type == "delins":
        _, vcf_pos, _, ref, alt = vcfhelper.VCFAlleleCreator(fasta).indel(
            chrom, start - 1, end, inserted=alt, deleted=ref
        )
        vcf_data.update({"pos": vcf_pos, "ref": ref, "alt": alt})
    else:
        raise RuntimeError("Unsupported variant type {}".format(variant_type))

    return vcf_data


class VcfInvalidVariantError(Exception):
    pass


class HGVScInvalidVariantError(Exception):
    pass


class TimeoutError(Exception):
    pass


def timeout_handler(*args, **kwargs):
    signal.alarm(0)
    raise TimeoutError("Function timed out")


signal.signal(signal.SIGALRM, timeout_handler)
