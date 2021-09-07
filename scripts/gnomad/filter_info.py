#!/usr/bin/env python3

import re
import sys
from enum import IntEnum


class VcfField(IntEnum):
    CHROM = 0
    POS = 1
    ID = 2
    REF = 3
    ALT = 4
    QUAL = 5
    FILTER = 6
    INFO = 7
    FORMAT = 8
    NORMAL = 9
    TUMOR = 10


def main() -> None:
    field_re = re.compile(r"(?:AF|AN|AC|nhomalt).*=")
    for line in sys.stdin:
        if line.startswith("#"):
            print(line, end="")
        elif line.strip() == "":
            print()
        else:
            fields = line.split("\t")[:8]
            fields[VcfField.ID] = "."
            try:
                filtered_fields = dict((f.split("=", 1)) for f in fields[VcfField.INFO].split(";") if field_re.match(f))
            except IndexError:
                breakpoint()
                pass
            if fields[VcfField.CHROM] in ("X", "Y") and is_nonpar(fields[VcfField.INFO]):
                new_fields = {}
                for ac_key in filtered_fields.keys():
                    if ac_key.startswith("AC_") and ac_key.endswith("_male"):
                        new_key = "_".join(["nhemialt", ac_key[3:-5]])
                        new_fields[new_key] = filtered_fields[ac_key]
                filtered_fields = {**filtered_fields, **new_fields}
            fields[VcfField.INFO] = ";".join(["=".join([k, v]) for k, v in filtered_fields.items()])
            print("\t".join(fields).rstrip("\n"))


def is_nonpar(info: str) -> bool:
    return info.startswith("nonpar;") or info.endswith(";nonpar") or ";nonpar;" in info


###

if __name__ == "__main__":
    main()
