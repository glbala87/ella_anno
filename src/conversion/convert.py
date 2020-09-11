
import re
from conversion.exporters import SeqPilotExporter, HGVScExporter

RE_SEQPILOT = re.compile(".*Transcript.*\tc. HGVS|.*c. HGVS.*\tTranscript")


def _is_seqpilot_format(input):
    with open(input, "r") as fd:
        header_line = None
        while not header_line:
            try:
                header_line = next(fd).strip()
            except StopIteration:
                raise RuntimeError("File %s is empty." % input)

    if RE_SEQPILOT.match(header_line):
        return True
    else:
        return False


def convert_to_vcf(input, output):
    # Determine if input is a SeqPilot export by looking at the header line
    is_seqpilot = _is_seqpilot_format(input)

    if is_seqpilot:
        exporter = SeqPilotExporter(input, output_vcf=output)
    else:
        exporter = HGVScExporter(input, output_vcf=output)

    # Convert input file to vcf
    exporter.parse()

    # Return report generated by the exporter. The results are available in the specified output file.
    return exporter.report()


if __name__ == "__main__":
    import sys

    input = sys.argv[1]
    output = sys.argv[2]

    exporter = convert_to_vcf(input, output)
    print(exporter)
