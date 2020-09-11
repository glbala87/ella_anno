"""
Tests have been extracted from ClinVar, and designed to represent a multitude of different variations. The VCF positions are validated using variantvalidator.org.
"""

import pytest
import tempfile
import os
import subprocess
from conversion.exporters import HGVScExporter
from conversion.conversion_utils import VcfInvalidVariantError


@pytest.fixture(scope="module")
def exporter():
    f = tempfile.NamedTemporaryFile(delete=False)
    yield HGVScExporter(f.name)
    os.remove(f.name)


VCF_TEMPLATE = "##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n{chrom}\t{pos}\t.\t{ref}\t{alt}\t.\t.\t.\n"


def vt_normalize(chrom, position, ref, alt):
    genome_file = os.environ["FASTA"]
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
    return chrom, position, ref, alt


def test_del(exporter):
    cases = {
        "NM_003159.2:c.1296_1298del": ("X", "18622338", "AAGT", "A"),
        "NM_001165963.2:c.2651_2656delGCAATT": ("2", "166894575", "GAATTGC", "G"),
        "NM_024422.4:c.2112_2116delAGCAT": ("18", "28651579", "AATGCT", "A"),
        "NM_001369.2:c.4702delC": ("5", "13862750", "CG", "C"),
        "NM_000890.4:c.-297_-291delCACACACinsGAGAGAGAGAGAGAGAG": (
            "11",
            "128761330",
            "CACACAC",
            "GAGAGAGAGAGAGAGAG",
        ),
        "NM_000098.2:c.72_97del26": (
            "1",
            "53662681",
            "TCGGCCCCTCAGCGCCGGCTCCGGGCC",
            "T",
        ),
        "NM_014363.5:c.9526_9528del": ("13", "23908486", "ATGT", "A"),
        "NM_000383.3:c.20_24del5": ("21", "45705905", "GCGCTA", "G"),
        "NM_007294.3:c.3339_3341del": ("17", "41244206", "TTCA", "T"),
    }

    for hgvsc, position in cases.items():
        d = exporter.hgvsc_to_vcfdict(hgvsc, "")
        normalized = vt_normalize(d["chr"], d["pos"], d["ref"], d["alt"])
        assert normalized == position


def test_delins(exporter):
    cases = {
        "NM_000455.4:c.597+17_597+19delinsCACGTGCTA": (
            "19",
            "1220521",
            "GGG",
            "CACGTGCTA",
        ),
        "NM_003482.3:c.9937_9939delCTTinsA": ("12", "49431200", "AAG", "T"),
        "NM_002065.6:c.*1910_*1913delAAGAinsTCATTTAAGT": (
            "1",
            "182351627",
            "TCTT",
            "ACTTAAATGA",
        ),
        "NM_000540.2:c.7835+6_7835+36delinsAGC": (
            "19",
            "38993373",
            "GCGGGGCAGGCTTCAGGGTGGGGCAGGGGCA",
            "AGC",
        ),
        "NM_021098.2:c.2209_2286del78insAGCAGA": (
            "16",
            "1254216",
            "GGTGACCGCTGGGACCCCACGCGACCACCCCGTGCGACGGACACACCAGGCCCAGGCCCAGGCAGCCCCCAGCGGCGG",
            "AGCAGA",
        ),
        "NM_001271.3:c.2785_2801del17insTG": (
            "15",
            "93522422",
            "GCCAAAAAGAAGATGGT",
            "TG",
        ),
        "NM_000059.3:c.8374_8384delCTTGGATTCTTinsAAG": (
            "13",
            "32944581",
            "CTTGGATTCTT",
            "AAG",
        ),
        "NM_005902.3:c.275_281delGGCGATGinsC": ("15", "67457301", "GGCGATG", "C"),
    }

    for hgvsc, position in cases.items():
        d = exporter.hgvsc_to_vcfdict(hgvsc, "")
        normalized = vt_normalize(d["chr"], d["pos"], d["ref"], d["alt"])
        assert normalized == position


def test_ins(exporter):
    cases = {
        "NM_024675.3:c.2142_2143insTAA": ("16", "23641332", "C", "CTTA"),
        "NM_000059.3:c.6662_6663insAAAG": ("13", "32915154", "A", "AAAAG"),
        "NM_007294.3:c.4571_4572insCC": ("17", "41226451", "A", "AGG"),
        "NM_007294.3:c.1964_1965insG": ("17", "41245583", "G", "GC"),
        "NM_000051.3:c.7655_7656insGA": ("11", "108202630", "C", "CAG"),
        "NM_003895.3:c.4215_4216insAATACT": ("21", "34003928", "A", "AAGTATT"),
    }

    for hgvsc, position in cases.items():
        d = exporter.hgvsc_to_vcfdict(hgvsc, "")
        normalized = vt_normalize(d["chr"], d["pos"], d["ref"], d["alt"])
        assert normalized == position


def test_inv(exporter):
    cases = {
        "NM_030813.5:c.1305_1307invGGG": ("11", "72012959", "CCC", "GGG"),
        "NM_000059.3:c.8979_8982inv": ("13", "32953912", "ATCA", "TGAT"),
        "NM_000527.4:c.762_763invGT": ("19", "11217308", "GT", "AC"),
        "NM_000320.2:c.*220_*221invTG": ("4", "17488533", "CA", "TG"),
        "NM_172218.2:c.2330_2331invTG": ("8", "101252680", "TG", "CA"),
        "NM_000020.2:c.653_654invGG": ("12", "52308250", "GG", "CC"),
        "NM_000249.3:c.2080_2081invGA": ("3", "37090485", "GA", "TC"),
        "NM_014000.2:c.1296_1297invAC": ("10", "75849900", "AC", "GT"),
        "NM_000540.2:c.1186_1187invGA": ("19", "38942467", "GA", "TC"),
        "NM_024422.4:c.2384_2385invAA": ("18", "28648983", "TT", "AA"),
        "NM_004168.3:c.1752_1753invAC": ("5", "251541", "AC", "GT"),
        "NM_002878.3:c.234_235invCA": ("17", "33445548", "TG", "CA"),
    }

    for hgvsc, position in cases.items():
        d = exporter.hgvsc_to_vcfdict(hgvsc, "")
        normalized = vt_normalize(d["chr"], d["pos"], d["ref"], d["alt"])
        assert normalized == position


def test_snp(exporter):
    cases = {
        "NM_000431.3:c.78+8G>A": ("12", "110012713", "G", "A"),
        "NM_001040108.1:c.2373G>A": ("14", "75513986", "C", "T"),
        "NM_004211.4:c.-41G>T": ("11", "20621178", "G", "T"),
        "NM_031226.2:c.*638G>T": ("15", "51502367", "C", "A"),
        "NM_020529.2:c.554C>T": ("14", "35872059", "G", "A"),
        "NM_000285.3:c.1045G>A": ("19", "33882308", "C", "T"),
        "NM_001083962.1:c.*5503T>C": ("18", "52889763", "A", "G"),
        "NM_000260.3:c.3262C>T": ("11", "76893622", "C", "T"),
        "NM_000069.2:c.5227-20C>T": ("1", "201009522", "G", "A"),
        "NM_198428.2:c.2488G>A": ("7", "33573755", "G", "A"),
        "NM_000548.4:c.657G>A": ("16", "2106653", "G", "A"),
        "NM_000744.6:c.1758+9C>T": ("20", "61980996", "G", "A"),
        "NM_003924.3:c.630G>T": ("4", "41748139", "C", "A"),
        "NM_020937.3:c.2497G>A": ("14", "45644454", "G", "A"),
        "NM_015265.3:c.287T>G": ("2", "200298120", "A", "C"),
        "NM_015909.3:c.758T>G": ("2", "15651463", "A", "C"),
    }

    for hgvsc, position in cases.items():
        d = exporter.hgvsc_to_vcfdict(hgvsc, "")
        normalized = vt_normalize(d["chr"], d["pos"], d["ref"], d["alt"])
        assert normalized == position


def test_dup(exporter):
    cases = {
        "NM_057179.2:c.229_234dupCAGCGC": ("2", "239757079", "G", "GAGCGCC"),
        "NM_133379.4:c.13660dup": ("2", "179613466", "A", "AT"),
        "NM_000527.4:c.1205dup": ("19", "11223970", "C", "CT"),
        "NM_007294.3:c.1378dup": ("17", "41246169", "A", "AT"),
        "NM_005149.2:c.603+41_603+48dupGTGTGTGT": ("1", "168262522", "A", "AGTGTGTGT"),
        "NM_001106.3:c.*4061dupA": ("3", "38528883", "C", "CA"),
        "NM_203447.3:c.3234+15dupC": ("9", "399267", "T", "TC"),
        "NM_001558.3:c.*356dupG": ("11", "117870710", "T", "TG"),
        "NM_001943.4:c.*611_*612dupTG": ("18", "29127305", "A", "AGT"),
    }

    for hgvsc, position in cases.items():
        d = exporter.hgvsc_to_vcfdict(hgvsc, "")
        normalized = vt_normalize(d["chr"], d["pos"], d["ref"], d["alt"])
        assert normalized == position


def test_identity(exporter):
    cases = {
        "NM_000431.3:c.78+8G=": ("12", "110012713", "G", "G"),
        "NM_001040108.1:c.2373G=": ("14", "75513986", "C", "C"),
        "NM_004211.4:c.-41G=": ("11", "20621178", "G", "G"),
    }
    for hgvsc, position in cases.items():
        with pytest.raises(VcfInvalidVariantError):
            exporter.hgvsc_to_vcfdict(hgvsc, "")
