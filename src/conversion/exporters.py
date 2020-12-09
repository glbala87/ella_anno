import signal
import re
import os
import datetime
import tempfile
import json
from collections import defaultdict

# Module for converting data
# Available on https://github.com/biocommons
import hgvs.parser
import hgvs.assemblymapper
import hgvs.dataproviders.uta
import hgvs.exceptions

# In addition, we need access to the reference genome. This is because
# the tools above will only convert to hgvsg. To generate vcf, we might need
# additional bases from the reference genome.
import pysam

from config import config
from .vcf_writer import VcfWriter
from .conversion_utils import (
    var_g_to_vcf,
    timeout_handler,
    VcfInvalidVariantError,
    HGVScInvalidVariantError,
)

import logging

logger = logging.getLogger("anno")

# Some HGVSc variants might hang during conversion. Setting a handler for
# timeout errors. This can be triggered with:
#
#   signal.alarm(5)
#   time.sleep(6)  # <-- Triggers the timeout handler which raises a TimeoutError
#   signal.alarm(0) # <-- Reset the timeout criteria. Functions run after this will not time out.
#
signal.signal(signal.SIGALRM, timeout_handler)

if "HGVS_SEQREPO_DIR" not in os.environ:
    with open(os.path.join(os.environ["ANNO_DATA"], "sources.json")) as sources_file:
        sources = json.load(sources_file)
        seqrepo_version = sources["seqrepo"]["version"]
        os.environ["HGVS_SEQREPO_DIR"] = os.path.join(
            os.environ["ANNO_DATA"], "seqrepo", seqrepo_version
        )

assert os.path.isdir(os.environ["HGVS_SEQREPO_DIR"]), "Path not found: {}".format(
    os.environ["HGVS_SEQREPO_DIR"]
)

if "UTA_DB_URL" not in os.environ:
    with open(os.path.join(os.environ["ANNO_DATA"], "sources.json")) as sources_file:
        sources = json.load(sources_file)
        uta_version = sources["uta"]["version"]
        port = os.getenv("PGPORT", 5432)
        os.environ["UTA_DB_URL"] = "postgresql://uta_admin@localhost:{}/uta/uta_{}".format(port, uta_version)


class Exporter(object):
    """
    Base class for exporters.
    """

    # Pattern to remove gene name from hgvsc, e.g.
    # NM_000059.3(BRCA2):c.486_488delGAG -> NM_000059.3:c.486_488delGAG
    HGVSC_REPLACE_PATTERN = re.compile(r"\(.*\)")

    def __init__(self, input, output_vcf=None):
        # Create the tools required for converting hgvsc to vcf
        self.FASTA = pysam.FastaFile(os.environ["FASTA"])
        self.HGVS_PARSER = hgvs.parser.Parser()
        self.UTA_CONNECTION = hgvs.dataproviders.uta.connect()
        self.VARIANT_MAPPER = hgvs.assemblymapper.AssemblyMapper(
            self.UTA_CONNECTION, assembly_name="GRCh37", replace_reference=True
        )

        self.data = open(input, "r")

        if output_vcf is None:
            tmp_f = tempfile.NamedTemporaryFile(suffix=".vcf", delete=False)
            tmp_f.close()
            output_vcf = tmp_f.name

        # Create the vcf writer to write the converted data to
        self.vcf_writer = VcfWriter(
            output_vcf,
            "Exported_{}".format(datetime.datetime.today().strftime("%Y-%m-%d")),
        )

        # Set up "recorders" for errors and lines successfully written
        self.errors = defaultdict(list)
        self.successful = 0

    def __convert(self, hgvsc):
        hgvsc = Exporter.HGVSC_REPLACE_PATTERN.sub("", hgvsc)
        try:
            var_c = self.HGVS_PARSER.parse_hgvs_variant(hgvsc)
        except Exception:
            if config["convert"]["fail_on_conversion_error"]:
                raise

        try:
            var_g = self.VARIANT_MAPPER.c_to_g(var_c)
        except hgvs.exceptions.HGVSInvalidVariantError as e:
            actual_ref = re.findall(
                r"Variant reference \([ACGT]+\) does not agree with reference sequence \(([ACGT]+)\)",
                e.message,
            )
            if config["convert"]["replace_ref_if_mismatch"] and actual_ref:
                logger.warning("%s: %s" % (hgvsc, str(e)))
                var_c.posedit.edit.ref = actual_ref[0]
                try:
                    var_g = self.VARIANT_MAPPER.c_to_g(var_c)
                except Exception:
                    if config["convert"]["fail_on_conversion_error"]:
                        raise
            elif config["convert"]["fail_on_conversion_error"]:
                raise

        return var_g

    def _convert_hgvsc(self, hgvsc):
        """
        Convert hgvsc to hgvsg, using the hgvs module (https://github.com/biocommons/hgvs)
        """

        signal.alarm(30)  # Set a 30 second timeout for the commands below
        try:
            var_g = self.__convert(hgvsc)
        except Exception as e:
            signal.alarm(0)
            raise type(e)("{}: {}".format(hgvsc, e.message))
        signal.alarm(0)
        return var_g

    def iter_data(self):
        for l in self.data:
            yield l.strip()

    def parse(self):
        raise NotImplementedError("Must be implemented in subclass")

    def get(self):
        return open(self.vcf_writer.path, "r")

    def hgvsc_to_vcfdict(self, hgvsc, comment):
        var_g = self._convert_hgvsc(hgvsc)
        vcf_data = var_g_to_vcf(var_g, self.FASTA)
        if vcf_data["ref"] == vcf_data["alt"]:
            raise VcfInvalidVariantError(
                "Not a variant. Reference {} matches alternate {}.".format(
                    vcf_data["ref"], vcf_data["alt"]
                )
            )
        vcf_data.update(
            {
                "comment": "{}_Original:{}".format(comment, hgvsc),
                "origin": hgvsc,
                "gt": "./.",
                "info": "",
            }
        )
        return vcf_data

    def report(self):
        s = "Number of lines successfully written: %d" % self.successful
        if self.errors:
            s += "\nErrors:\n"
            for k, v in sorted(
                list(self.errors.items()), cmp=lambda x, y: len(y[1]) - len(x[1])
            ):
                s += "{:<30}\t{:>6}\n".format(k, len(v))
        else:
            s += " (no errors)\n"
        return s

    def __del__(self):
        self.UTA_CONNECTION.close()
        self.data.close()


class HGVScExporter(Exporter):
    RE_HGVSC = re.compile(r"(?P<hgvsc>.+:c\.[^\s]+)(\s+\((?P<GT>.+)?\))?")
    """
    Class to convert a file of line-separated HGVSc-variants to vcf
    """

    def iter_data(self):
        for l in self.data:
            try:
                m = HGVScExporter.RE_HGVSC.match(l)
                if m is None:
                    raise HGVScInvalidVariantError(
                        "Unable to extract hgvsc from {}".format(l)
                    )
            except Exception:
                if config["convert"]["fail_on_conversion_error"]:
                    raise
                continue
            yield m.group("hgvsc"), m.group("GT")

    def parse(self, comment="HGVScExport"):
        gt_mapping = {"het": "0/1", "homo": "1/1", "hom": "1/1"}
        with self.vcf_writer:
            for hgvsc, gt in self.iter_data():
                try:
                    vcf_data = self.hgvsc_to_vcfdict(hgvsc, comment)
                except Exception as e:
                    if config["convert"]["fail_on_conversion_error"]:
                        raise
                    logger.warning(e.__class__.__name__, hgvsc, e.message)
                    self.errors[e.__class__.__name__].append((hgvsc, e.message))
                    continue

                gt_vcf = gt_mapping.get(gt)
                if gt_vcf:
                    vcf_data.update({"gt": gt_vcf})

                self.vcf_writer.write_data(vcf_data)
                self.successful += 1
        assert self.successful > 0, "No lines written to vcf"


class SeqPilotExporter(Exporter):
    """
    Exports an SeqPilot-exported file to vcf format for importing to VarDB.
    """

    def iter_data(self):
        header = None
        for line in self.data:
            line = line.strip()
            if header is None:
                header = line.split("\t")
                continue
            yield {k: v for k, v in zip(header, line.split("\t"))}

    def parse(self, comment="SeqPilotExport"):
        gt_mapping = {"het": "0/1", "homo": "1/1", "hom": "1/1"}
        with self.vcf_writer:
            for line in self.iter_data():

                hgvsc = "{tx}:{hgvsc}".format(
                    tx=line["Transcript"], hgvsc=line["c. HGVS"]
                )
                try:
                    gt = re.findall(r"[ACGT]*\((.*)\)", line["Nuc Change"])[0]
                    gt_vcf = gt_mapping[gt]
                except Exception:
                    gt_vcf = "./."

                try:
                    vcf_data = self.hgvsc_to_vcfdict(hgvsc, comment)
                except Exception as e:
                    if config["convert"]["fail_on_conversion_error"]:
                        raise
                    logger.warning("%s: %s" % (hgvsc, str(e)))
                    self.errors[e.__class__.__name__].append((hgvsc, e.message))
                    continue

                vcf_data.update({"gt": gt_vcf})

                self.vcf_writer.write_data(vcf_data)
                self.successful += 1

        assert self.successful > 0, "No lines written to vcf"
