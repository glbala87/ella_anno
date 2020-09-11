
import sys
import gzip
import re
import argparse
from os.path import expanduser

"""
This module parses the PubMed IDs from a vcf[.gz] file.
"""


class PmidFromVcf(object):

    RE_PMID = re.compile(r"pmid=(\d+)[;\t]")
    RE_EXTRAREFS = re.compile(r"(extrarefs=[^;]+[;\t])")
    RE_EXTRAREFS_PARSER = re.compile(r"(\d+)\|[^;,]+[,;\t]")

    def _parse_pmids(self, f, modes=["_pmids", "_extrarefs"]):
        """
        :param f: An opened file object
        :param modes: List of parse modes ["_pmid", "_extrarefs"]
        :return: List of PubMed IDs
        """
        pmids = set([])
        for line in f:
            if "_extrarefs" in modes:
                extrarefs_match = PmidFromVcf.RE_EXTRAREFS.search(line)
                if extrarefs_match:
                    pmids |= set(PmidFromVcf.RE_EXTRAREFS_PARSER.
                                 findall(extrarefs_match.group(1)))
            if "_pmids" in modes:
                pmid_match = PmidFromVcf.RE_PMID.search(line)
                if pmid_match:
                    pmids |= set([pmid_match.group(1)])
        return pmids

    def parse_pmids(self, vcf_file):
        """
        :param vcf_file: Name of vcf[.gz]-file
        :return: Opens file for reading
        """
        if vcf_file.endswith('.gz'):
            with gzip.open(vcf_file, 'r') as f:
                pmids = self._parse_pmids(f)
        else:
            with open(vcf_file, 'r') as f:
                pmids = self._parse_pmids(f)

        return list(pmids)

    def parse_and_save_pmids(self, vcf_file, pmid_file):
        """
        :param vcf_file: Name of vcf[.gz]-file
        :return: PubMed IDs and saves them to file
        """
        pmids = self.parse_pmids(vcf_file)
        self.save_pmids(pmid_file, pmids)
        return pmids


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse Pubmed IDs from file")
    parser.add_argument('infile', type=str,
                        help='Chose HGMD database: name.vcf[.gz]')
    parser.add_argument('-o', '--outfile', type=str,
                        const='pubmed_ids_hgmd.txt',
                        default=argparse.SUPPRESS,
                        nargs='?', help='provide file name to save pmids')
    args = parser.parse_args()

    pmid_parser = PmidFromVcf()
    pmids = pmid_parser.parse_pmids(expanduser(args.infile))
    for pmid in pmids:
        print(pmid)
