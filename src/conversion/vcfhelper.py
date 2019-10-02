"""
Module for VCF helper functions.

Methods in VCFAlleleCreator class can create correct alleles and vcf position
which is useful when making VCF files from scratch.
"""

import sys


class VCFAlleleCreator(object):
    """
    Creates first VCF fields (chromosome, position, ref, alt, id)
    given zero-based genomic positions.
    Verifies that given reference matches what is found in genome at given coordinates.
    """

    def __init__(self, seqdb, useGenomeRef=True):
        self.seqdb = seqdb
        self.useGenomeRef = useGenomeRef
        self.refMismatch = []

    def _refMatch(self, refAtPosition, ref):
        return refAtPosition == ref

    def snp(self, chromosome, gPos, ref, alt, id="."):
        """Given zero-based genomic position and other SNP data, return VCF SNP data."""
        assert len(ref) == len(alt) == 1
        assert gPos >= 0
        refAtPosition = str(self.seqdb[chromosome][gPos : gPos + 1]).upper()
        if not self._refMatch(refAtPosition, ref):
            self.refMismatch.append(
                ("SNP", refAtPosition, chromosome, gPos, ref, alt, id)
            )
        vcfPosition = gPos + 1
        if self.useGenomeRef:
            return chromosome, str(vcfPosition), id, refAtPosition, alt
        else:
            return chromosome, str(vcfPosition), id, ref, alt

    def insertion(self, chromosome, gPos, inserted, id="."):
        """Returns VCF insertion data.

        Note that gPos is 0-position before insertion, i.e. the first base in the VCF alleles."""
        assert gPos >= 0
        firstBase = str(self.seqdb[chromosome][gPos : gPos + 1]).upper()
        ref = firstBase
        alt = firstBase + inserted
        vcfPosition = gPos + 1
        return chromosome, str(vcfPosition), id, ref, alt

    def deletion(self, chromosome, gPosStart, gPosEnd, deleted="", id="."):
        """Returns VCF deletion data.

        Note that gPosStart is 0-position at first deleted base,
        gPosEnd is pos after last deleted base (i.e. half-open interval).
        """
        assert gPosStart >= 0 and gPosEnd > 0
        refAtPosition = str(self.seqdb[chromosome][gPosStart:gPosEnd]).upper()
        if deleted != "":
            if len(deleted) != gPosEnd - gPosStart or not self._refMatch(
                refAtPosition, deleted
            ):
                self.refMismatch.append(
                    ("DEL", refAtPosition, chromosome, gPosStart, gPosEnd, deleted, id)
                )
        firstBase = str(self.seqdb[chromosome][gPosStart - 1 : gPosStart]).upper()
        vcfPosition = gPosStart + 1 - 1
        ref = (
            firstBase + deleted
            if deleted != "" and not self.useGenomeRef
            else firstBase + refAtPosition
        )
        alt = firstBase
        return chromosome, str(vcfPosition), id, ref, alt

    def indel(self, chromosome, gPosStart, gPosEnd, inserted, deleted="", id="."):
        """Returns VCF indel data. Positions as for deletion."""
        assert gPosStart >= 0 and gPosEnd > 0
        refAtPosition = str(self.seqdb[chromosome][gPosStart:gPosEnd]).upper()
        if deleted != "":
            if len(deleted) != gPosEnd - gPosStart or not self._refMatch(
                refAtPosition, deleted
            ):
                self.refMismatch.append(
                    (
                        "INDEL",
                        refAtPosition,
                        chromosome,
                        gPosStart,
                        gPosEnd,
                        inserted,
                        deleted,
                        id,
                    )
                )
        firstBase = str(self.seqdb[chromosome][gPosStart - 1 : gPosStart]).upper()
        vcfPosition = gPosStart + 1 - 1
        ref = (
            firstBase + deleted
            if deleted != "" and not self.useGenomeRef
            else firstBase + refAtPosition
        )
        alt = firstBase + inserted
        return chromosome, str(vcfPosition), id, ref, alt

    def duplication(self, chromosome, gPosStart, gPosEnd, duplicated="", id="."):
        """Returns VCF duplication data. Positions as for deletion."""
        assert gPosStart >= 0 and gPosEnd > 0
        refAtPosition = str(self.seqdb[chromosome][gPosStart:gPosEnd]).upper()
        if duplicated != "":
            if len(duplicated) != gPosEnd - gPosStart or not self._refMatch(
                refAtPosition, duplicated
            ):
                self.refMismatch.append(
                    (
                        "DUP",
                        refAtPosition,
                        chromosome,
                        gPosStart,
                        gPosEnd,
                        duplicated,
                        id,
                    )
                )
        vcfPosition = gPosStart + 1
        ref = (
            duplicated if duplicated != "" and not self.useGenomeRef else refAtPosition
        )
        alt = ref + ref
        return chromosome, str(vcfPosition), id, ref, alt

    def write_records_failing_reference_match(self, fileHandle=sys.stderr):
        """Write data of those calls that had given reference data not matching the reference genome.

        If there are any, these should be checked as there is most likely an error in the input data.
        """
        for r in self.refMismatch:
            fileHandle.write("\t".join((str(e) for e in r)) + "\n")
