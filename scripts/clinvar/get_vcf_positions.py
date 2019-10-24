import os
import subprocess


VCF_TEMPLATE = (
    "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\t.\t.\n"
)


def vt_normalize(chrom, position, ref, alt, genome_file):
    with open(os.devnull, "wb") as DEVNULL:
        p = subprocess.Popen(
            ["vt", "normalize", "-n", "-r", genome_file, "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=DEVNULL,
        )
        p.stdin.write(VCF_TEMPLATE.format(chrom=chrom, pos=position, ref=ref, alt=alt))
        output = p.communicate()[0]
    chrom, position, _, ref, alt, _, _, _ = output.splitlines()[-1].split("\t")
    return chrom, int(position), ref, alt


def scalar_xpath(root, path, cast=None, require=False, **kwargs):
    v = root.xpath(path, **kwargs)
    if require:
        assert len(v) == 1
    else:
        assert len(v) <= 1

    if len(v) == 0:
        return None
    else:
        v = v[0]
        if cast is not None:
            return cast(v)
        else:
            return v


def deletion(genome, chrom, position, variant_length):
    ref = str(genome.get_seq(chrom, position, position + variant_length))
    alt = str(genome.get_seq(chrom, position, position))
    return ref, alt


def insertion(genome, chrom, position, alt):
    ref = str(genome.get_seq(chrom, position, position))
    alt = ref + alt
    return ref, alt


def indel(genome, chrom, position, variant_length, alt):
    ref = str(genome.get_seq(chrom, position, position + variant_length))
    alt = str(genome.get_seq(chrom, position, position)) + alt
    return ref, alt


def duplication(genome, chrom, position, variant_length):
    ref = str(genome.get_seq(chrom, position, position))
    alt = str(genome.get_seq(chrom, position, position + variant_length))
    return ref, alt


def inversion(genome, chrom, position, variant_length):
    ref = str(genome.get_seq(chrom, position, position + variant_length))
    alt = ""
    for c in reversed(ref):
        if c == "A":
            alt += "T"
        elif c == "G":
            alt += "C"
        elif c == "T":
            alt += "A"
        elif c == "C":
            alt += "G"

    return ref, alt


def get_vcf_positions(genome, allele):
    variant_type = scalar_xpath(allele, "VariantType/text()", require=True)

    seq_locs = allele.xpath("./SequenceLocation[@Assembly='GRCh37']")
    keys = []
    for seq_loc in seq_locs:
        chrom = scalar_xpath(seq_loc, "@Chr", smart_strings=False, require=True)
        position = scalar_xpath(seq_loc, "@start", smart_strings=False, cast=int, require=True)
        ref = scalar_xpath(seq_loc, "@referenceAllele", smart_strings=False)
        alt = scalar_xpath(seq_loc, "@alternateAllele", smart_strings=False)

        if ref == "-":
            ref = None
        if alt == "-":
            alt = None

        # For some SNVs, ref is not specified. Fetch ref in those cases.
        if not ref and variant_type == "single nucleotide variant":
            ref = str(genome.get_seq(chrom, position, position))

        end = scalar_xpath(seq_loc, "@stop", smart_strings=False, cast=int, require=True)
        variant_length = end - position

        if not ref and not alt:

            # Variant type is deletion or duplication
            # A GRCh38 insertion translates to a duplication in GRCh37 if no reference allele provided
            if variant_type == "Insertion":
                variant_type = "Duplication"
            assert variant_type in ["Deletion", "Duplication", "Inversion"]
            if variant_type == "Deletion":
                position, variant_length = position - 1, variant_length + 1
                ref, alt = deletion(genome, chrom, position, variant_length)
            elif variant_type == "Duplication":
                position, variant_length = position - 1, variant_length + 1
                ref, alt = duplication(genome, chrom, position, variant_length)
            elif variant_type == "Inversion":
                ref, alt = inversion(genome, chrom, position, variant_length)
        elif alt and not ref:
            # Variant type is insertion or indel

            # A GRCh38 duplication translates to an insertion in GRCh37 if no alternate allele provided
            if variant_type == "Duplication":
                if variant_length > 1:
                    position, variant_length = position - 1, variant_length + 1
                variant_type = "Insertion"
            assert variant_type in ["Insertion", "Indel"]
            if variant_type == "Insertion":
                ref, alt = insertion(genome, chrom, position, alt)
            elif variant_type == "Indel":
                position, variant_length = position - 1, variant_length + 1
                ref, alt = indel(genome, chrom, position, variant_length, alt)
        elif ref and not alt:
            # Variant type is deletion
            assert variant_type == "Deletion"
            position, variant_length = position - 1, variant_length + 1
            ref, alt = deletion(genome, chrom, position, variant_length)

        # Change ref to genome ref if not equal
        actual_ref = str(genome.get_seq(chrom, position, position + len(ref) - 1))
        if actual_ref != ref:
            ref = actual_ref

        if len(ref) > 1 or len(alt) > 1:
            chrom, position, ref, alt = vt_normalize(chrom, position, ref, alt, genome.filename)

        keys.append((chrom, position, ref, alt))
    return list(set(keys))
