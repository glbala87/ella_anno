import os
import pysam


class IncorrectReferenceError(RuntimeError):
    pass


class VCFCheckRef(object):
    def __init__(self):
        self.fasta = pysam.FastaFile(os.environ["FASTA"])

    def check(self, vcf_file):
        with open(vcf_file, "r") as input:
            i = 0
            for l in input.xreadlines():
                if l.startswith("#") or not l:
                    continue
                i += 1
                chrom, pos, _, vcf_ref = l.split("\t")[:4]
                pos = int(pos) - 1
                actual_ref = self.fasta.fetch(chrom, pos, pos + len(vcf_ref))
                if str(actual_ref) != vcf_ref:
                    raise IncorrectReferenceError(
                        "Genome reference ({}) does not match vcf reference ({}). Offending line is: {} ".format(
                            actual_ref, vcf_ref, l
                        )
                    )


if __name__ == "__main__":
    import sys

    vcf_file = sys.argv[1]
    VCFCheckRef().check(vcf_file)
