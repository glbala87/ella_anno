import sys
import json
import base64
import re
import gzip

if __name__ == "__main__":
    clinvar_vcf = sys.argv[1]
    pubmed_ids = set()
    if clinvar_vcf.endswith(".gz"):
        _open = gzip.open
    else:
        _open = open
    with _open(clinvar_vcf, "rt") as f:
        for l in f:
            if l.startswith("#"):
                continue
            m = re.match(".*?CLINVARJSON=([A-F0-9]*)", l)
            data = json.loads(base64.b16decode(m.groups()[0]))
            pubmed_ids |= set(data["pubmed_ids"])

    for pmid in sorted([int(x) for x in pubmed_ids]):
        print(pmid)

