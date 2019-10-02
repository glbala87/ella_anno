VCF_HEADER = """##fileformat=VCFv4.1
##INFO=<ID=class,Number=.,Type=String,Description="class">
##INFO=<ID=HGVSC_ORIGIN,Number=.,Type=String,Description="HGVSc that was origin for this vcf line. For audit purposes.">
##FORMAT=<ID=GT,Number=1,Type=String,Description="Genotype">
#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\t{sample}
"""


class VcfWriter(object):

    # 13  32890572    .  G   A   .   .   class=1;ASSC=;ASSINTERPRETER=;   GT  ./.
    VCF_LINE = (
        "{chr}\t{pos}\t.\t{ref}\t{alt}\t.\t.\tHGVSC_ORIGIN={origin};{info}\tGT\t{gt}\n"
    )

    def __init__(self, path, sample):
        self.path = path
        self.sample = sample
        self.fd = None
        self.header_written = False

    def __enter__(self):
        if not self.fd:
            self.fd = open(self.path, "w")
        if not self.header_written:
            self.write_header()

    def __exit__(self, type, value, traceback):
        if self.fd:
            self.fd.close()

    def write_header(self):
        if not self.fd:
            self.fd = open(self.path, "w")
        self.fd.write(VCF_HEADER.format(sample=self.sample))
        self.header_written = True

    @staticmethod
    def convert_to_line(data):
        return VcfWriter.VCF_LINE.format(**data)

    def write_data(self, data):
        if not self.fd:
            self.fd = open(self.path, "a")
        self.fd.write(self.convert_to_line(data))

    def close(self):
        self.fd.close()
