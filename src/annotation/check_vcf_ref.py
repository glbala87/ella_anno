from pygr.seqdb import SequenceFileDB
import os


class IncorrectReferenceError(RuntimeError):
    pass


class VCFCheckRef(object):
    def __init__(self):
        self.SEQ_DB = SequenceFileDB(os.environ["FASTA"])

    def check(self, vcf_file):
        with open(vcf_file, "r") as input:
            i = 0
            for l in input.xreadlines():
                if l.startswith("#") or not l:
                    continue
                i += 1
                lsplit = l.split("\t")
                actual_ref = self.SEQ_DB[lsplit[0]][
                    int(lsplit[1]) - 1 : int(lsplit[1]) + len(lsplit[3]) - 1
                ]
                if str(actual_ref) != lsplit[3]:
                    raise IncorrectReferenceError(
                        "Genome reference ({}) does not match vcf reference ({}). Offending line is: {} ".format(
                            actual_ref, lsplit[3], l
                        )
                    )


if __name__ == "__main__":
    import sys

    vcf_file = sys.argv[1]
    VCFCheckRef().check(vcf_file)
