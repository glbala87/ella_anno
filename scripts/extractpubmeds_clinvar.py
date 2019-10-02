from __future__ import print_function
import sys
import os
import argparse
import gzip
import json
import base64
import re
from IPython import embed
from os.path import expanduser


def open_vcf_file(filename):
    "Open vcf-file with gzip or open, depending on extension"
    if filename.endswith('.gz'):
        f = gzip.open(filename, 'r')
    else:
        f = open(filename, 'r')

    return f

def extract_clinvar_pubmeds(filename):
    "Extract all ClinVar PubMed IDs from formatted vcf-file"
    f = open_vcf_file(filename)
    it = iter(f)
    for l in it:
        if "#CHROM" in l:
            break

    pubmed_ids = []
    info_pattern = re.compile(r"CLINVARJSON=([^;]+)")
    for i, l in enumerate(it):
        info = l.split('\t')[7]
        # key, clinvarjson = info.split('=')
        # assert key == "CLINVARJSON"
        clinvarjson = info_pattern.match(info).group(1)
        clinvarjson = clinvarjson.strip()
        clinvarjson = json.loads(base64.b16decode(clinvarjson))
        # pubmed_ids += clinvarjson["pubmed_ids"]
        pubmed_ids += clinvarjson["pubmeds"]
        # for item in clinvarjson["rcvs"].values():
        #     pubmed_ids += item["pubmed"]
    # return set(pubmed_ids)
    return pubmed_ids


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('clinvar', type=str,
                        help="Chose ClinVar database: name.vcf[.gz]")
    parser.add_argument('-o', '--outfile', type=str,
                        const='pubmed_ids_clinvar.txt',
                        default=argparse.SUPPRESS,
                        nargs='?', help='provide file name to save pmids')
    args = parser.parse_args()
    import time
    t1 = time.time()
    pubmed_ids = extract_clinvar_pubmeds(expanduser(args.clinvar))
    unique_pubmed_ids = set(pubmed_ids)
    for pid in unique_pubmed_ids:
        print(pid)
    t2 = time.time()

    print("Extracted %d (%d unique) pubmed ids in %f seconds" % (len(pubmed_ids), len(unique_pubmed_ids), t2-t1), file=sys.stderr)
