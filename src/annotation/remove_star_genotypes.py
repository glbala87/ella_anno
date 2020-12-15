import sys
import re


def order_genotype(gt):
    "Order genotype. E.g. 1/0 -> 0/1"
    # Do not order phased genotypes
    if "/" not in gt:
        return gt
    gt0, gt1 = gt.split("/")
    try:
        gt0 = int(gt0)
        gt1 = int(gt1)
    except ValueError as e:
        # Do not apply any order to genotypes containing '.'
        return gt
    return f"{min(gt0,gt1)}/{max(gt0,gt1)}"


def remove_star_alleles(f):
    it = iter(f)

    # Iterate over header
    for l in it:
        print(l.rstrip("\n"))
        if l.startswith("#CHROM"):
            break

    # Iterate over body
    for line in it:
        columns = line.split("\t")
        alts = columns[4].split(",")
        if "*" not in alts:
            print(line)
            continue

        # We fetch the allele index here to modify the genotype only
        # Leave the removal of the star allele to bcf-tools
        allele_index = alts.index("*")
        fmat = columns[8].split(":")
        if "GT" not in fmat:
            # This shouldn't happen, but leave it to other tools to handle
            print(line)
            continue

        gt_index = fmat.index("GT")
        for i in range(9, len(columns)):
            fmat_data = columns[i].rstrip("\n").split(":")

            # Change genotype referring to star allele to refer to reference instead.
            # Note: This is not correct, but the overlapping deletion should also be in the VCF with a complementing genotype
            gt_removed_star_allele = re.sub(str(allele_index + 1), "0", fmat_data[gt_index])

            # Order genotype (e.g. 1/0 -> 0/1)
            fmat_data[gt_index] = order_genotype(gt_removed_star_allele)
            columns[i] = ":".join(fmat_data)

        # Print out fixed line
        print("\t".join(columns))


if __name__ == "__main__":
    if len(sys.argv) > 1:
        input = open(sys.argv[1], "r")
    else:
        input = sys.stdin

    remove_star_alleles(input)
