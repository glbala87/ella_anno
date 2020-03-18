#!/usr/bin/env python
from __future__ import print_function

"""
Read ClinVar XML data and parse into vcf-file.

We wish to accurately represent the data available on the website. ClinVar provides multiple data sources for its data, but none of them seems to be complete.
For as complete solution as possible, we use the efetch utility from entrez (https://www.ncbi.nlm.nih.gov/books/NBK25499/#_chapter4_EFetch_). This gives, as far as I can tell,
the complete data for what's shown at the website, per variation.

From the XML results returned here, we attempt to calculate the VCF position(s) of each variation.
However, if the ClinVar vcf provides a different position for that variant, we fall back to this.

Other data sources evaluated:
# VCF incomplete (lacking ~600 variant that I could parse from ClinVarFullRelease.xml). In addition, no submitter data available.
# -- Example variant ids missing from vcf: 208614, 556489 (inserted alleles given in GRCh37), 598978, 217477
# ClinVarFullRelease.xml incomplete. Doesn't have aggregated review status, and this must be computed. However, some SCVs are not present in this (e.g. SCV000077247 for variation id 2300), which makes this impossible.
# variation_archive_xxxxxx.xml.gz incomplete. Also lacks e.g. SCV000077247 for variation id 2300

For each variant, dump json data (b16 encoded) under the INFO-column in the vcf in the
ID CLINVARJSON. The data is then stored in a dict as

    ["rcvs"][scv_id][metadata_tag]=value

Each variant can have multiple SCVs.
NOTE: We store it under "rcvs" for backward compatibility - however, we do NOT store the actual RCV. Sorry for the confusion.

Each position in the VCF should have only one variation id associated with it, however, in some edge cases, the same variation ID can have multiple positiions.

By default, the fetched data from the entrez API, is archived for possible later inspection, as this is not archived on the ClinVar ftp servers.

Requirements (Python packages):
- lxml
- jsonschema

Requirements (command line tools):
- vcftools (vcf-validator, vcf-sort)
- bgzip

"""

import argparse
import base64
import httplib
import datetime
import json
import jsonschema
import multiprocessing
import logging
import os
import re
import signal
import subprocess
import sys
import tarfile
import traceback
import urllib2
from collections import defaultdict
from cStringIO import StringIO
from lxml import etree
from multiprocessing.pool import Pool

from variation_archive_parser import VariationArchiveParser
from utils import vcf_sort, vcf_validator, bgzip, tabix, open_file


class IncompatibleDataError(RuntimeError):
    pass


class TimeoutError(RuntimeError):
    pass


def timeout(*args):
    raise TimeoutError("Timed out")


# Register timeout to be executed if SIGALRM is triggered.
# This is used to timeout potentially hanging processes
signal.signal(signal.SIGALRM, timeout)

TODAY = datetime.datetime.today().strftime("%d/%m/%Y")

# API KEY for entrez utilities (https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/)
API_KEY = os.environ.get("ENTREZ_API_KEY")

# Max retries for each batch, and which errors should trigger a retry
MAX_RETRIES = 10
RETRY_ERRORS = [httplib.IncompleteRead, urllib2.HTTPError, urllib2.URLError, TimeoutError]

# Schema used in ELLA on Clinvar annotation. The dict encoded in the field CLINVARJSON should adher to this schema.
CLINVAR_V1_SCHEMA = {
    "definitions": {
        "rcv": {
            "$id": "#/definitions/rcv",
            "type": "object",
            "required": ["traitnames", "clinical_significance_descr", "variant_id", "submitter", "last_evaluated"],
            "properties": {
                "traitnames": {"type": "array", "items": {"type": "string"}},
                "clinical_significance_descr": {"type": "array", "items": {"type": "string"}},
                "variant_id": {"type": "array", "items": {"type": "string"}},
                "submitter": {"type": "array", "items": {"type": "string"}},
            },
        }
    },
    "$schema": "http://json-schema.org/draft-07/schema#",
    "$id": "http://example.com/root.json",
    "type": "object",
    "required": ["variant_description", "variant_id", "rcvs"],
    "properties": {
        "variant_description": {"$id": "#/properties/variant_description", "type": "string"},
        "variant_id": {"$id": "#/properties/variant_id", "type": "integer"},
        "rcvs": {"type": "object", "patternProperties": {"": {"$ref": "#/definitions/rcv"}}},
    },
}


def _convert_alts(original_positions):
    # Convert positions where alt is in ALT_TRANSLATIONS
    # E.g. where for key ("1", 123, "A", "Y"), drop position in favour of ("1", 123, "A", "C") and ("1", 123, "A", "T")
    ALT_TRANSLATIONS = {
        "N": ["A", "C", "G", "T"],
        "B": ["C", "G", "T"],
        "D": ["A", "G", "T"],
        "H": ["A", "C", "T"],
        "V": ["A", "C", "G"],
        "R": ["A", "G"],
        "Y": ["C", "T"],
        "S": ["G", "C"],
        "W": ["A", "T"],
        "K": ["G", "T"],
        "M": ["A", "C"],
    }
    positions = set()
    for chrom, pos, ref, alt in original_positions:
        if alt not in ALT_TRANSLATIONS:
            positions.add((chrom, pos, ref, alt))
        else:
            converted_positions = set(
                [(chrom, pos, ref, new_alt) for new_alt in ALT_TRANSLATIONS[alt] if new_alt != ref]
            )
            positions |= converted_positions

    return positions


def clinvar_vcf_check(data, clinvar_vcf):
    "Check parsed data from VariationArchiveParser against parsed clinvar vcf"

    variant_id = data["variant_id"]
    variation_type = data["variation_type"]
    xml_positions = _convert_alts(data["positions"])
    if variant_id in clinvar_vcf:
        vcf_positions = _convert_alts([clinvar_vcf[variant_id]["position"]])
    else:
        vcf_positions = set()

    # Determine which positions to use. In most cases, the XML positions will match the positions from the VCF
    if not vcf_positions and not xml_positions:
        raise IncompatibleDataError(
            "No positions found for variant id {} (type: {})".format(variant_id, variation_type)
        )

    elif vcf_positions and not xml_positions:
        # Using vcf positions
        logging.debug("Could not find position in XML. Using clinvar vcf position for {}".format(variant_id))
        data["variation_warnings"].append("WARN_FAILED_TO_CALCULATE_POSITION")
        data["positions"] = vcf_positions

    elif xml_positions and not vcf_positions:
        # Using XML positions
        logging.debug("Could not find position in VCF. Using XML position for {}".format(variant_id))
        data["variation_warnings"].append("WARN_VARIANT_ID_NOT_IN_CLINVAR_VCF")
        data["positions"] = xml_positions

    elif vcf_positions != xml_positions:
        # Found data in both XML and VCF, but they do not match...
        logging.debug(
            "Position does not match clinvar position for variant id {}. Using clinvar vcf position.\n".format(
                variant_id
            )
            + "-- Clinvar: {}\n".format(vcf_positions)
            + "-- Calculated: {}\n".format(xml_positions)
        )
        data["variation_warnings"] += [
            "WARN_CALCULATED_POSITION_MISMATCH=" + ",".join("{}:{}:{}/{}".format(*k) for k in xml_positions)
        ]
        data["positions"] = vcf_positions

    else:
        # Assert that they are equal (most cases)
        assert vcf_positions and xml_positions and vcf_positions == xml_positions
        data["positions"] = xml_positions

    if len(data["positions"]) > 1:
        data["variation_warnings"].append("WARN_MULTIPLE_POSITIONS")

    # Skip haplotypes/compound heterozygous variations, as these might consist of alleles that are submitted as standalone variations
    # Some haplotypes are reported with a single allele. These will be kept.
    if len(data["positions"]) > 1 and variation_type in [
        "Haplotype",
        "Compound heterozygote",
        "Phase unknown",
        "Diplotype",
    ]:
        assert (
            variant_id not in clinvar_vcf
        ), "Variant id {} is in clinvar vcf, but XML data suggests multiple positions".format(variant_id)
        raise IncompatibleDataError(
            "Variant {} has variant type {} with {} positions.".format(
                variant_id, variation_type, len(data["positions"])
            )
        )

    # Check that XML clnsig and revstat match VCF
    if variant_id in clinvar_vcf and (clinvar_vcf[variant_id]["clnsig"], clinvar_vcf[variant_id]["revstat"]) != (
        data["clnsig"],
        data["revstat"],
    ):
        data["variation_warnings"].append(
            "WARN_CLINVAR_VCF_CLNSIG_REVSTAT_MISMATCH={}:{}".format(
                clinvar_vcf[variant_id]["clnsig"], clinvar_vcf[variant_id]["revstat"]
            )
        )
        logging.debug(
            "clnsig and revstat not matching clinvar vcf for variant id {}:\n".format(variant_id)
            + "-- ClinVar VCF: {}\n".format((clinvar_vcf[variant_id]["clnsig"], clinvar_vcf[variant_id]["revstat"]))
            + "-- Fetched from XML: {}".format((data["clnsig"], data["revstat"]))
        )

    return data


def get_vcf_lines(data):
    json_data = {
        "variant_id": int(data["variant_id"]),
        "rcvs": data["submissions"],
        "pubmed_ids": data["pubmed_ids"],
        "variant_description": data["revstat"],
    }
    jsonschema.validate(json_data, CLINVAR_V1_SCHEMA)
    b16_info = base64.b16encode(json.dumps(json_data, separators=(",", ":")))
    vcf_lines = []
    if not data["variation_warnings"]:
        vcf_variation_warnings = ""
    else:
        vcf_variation_warnings = ";" + ";".join(data["variation_warnings"])

    for chrom, position, ref, alt in data["positions"]:
        if ref == alt:
            # Skip non-variants
            logging.debug(
                "Non-variant found {} (variant id: {})".format((chrom, position, ref, alt), data["variant_id"])
            )
            continue

        elif not (set(ref).issubset(set("ACGT")) and set(alt).issubset(set("ACGT"))):
            # Skip variants where ref or alt is not well defined
            logging.debug(
                "Variant not well defined {}. Variant id: {}".format((chrom, position, ref, alt), data["variant_id"])
            )
            continue

        vcf_lines.append(
            "{chrom}\t{pos}\t{variant_id}\t{ref}\t{alt}\t5000\tPASS\tVARIATION_TYPE={variation_type};VARIATION_ID={variant_id};CLNSIG={clnsig};CLNREVSTAT={revstat};CLINVARJSON={info}{variation_warnings}".format(
                chrom=chrom,
                pos=position,
                variant_id=data["variant_id"],
                ref=ref,
                alt=alt,
                variation_type=data["variation_type"].replace(" ", "_"),
                clnsig=data["clnsig"].replace(" ", "_"),
                revstat=data["revstat"].replace(" ", "_"),
                info=b16_info,
                variation_warnings=vcf_variation_warnings,
            )
        )
    return vcf_lines


def xml_to_vcf(xml, clinvar_vcf, archive_folder):
    """
    Read all VariationReport tags and attempt to create one or more vcf lines from it. Return all vcf lines extracted from xml.
    """
    tree = etree.iterparse(StringIO(xml), tag="VariationArchive", events=["end"])

    vcf_lines = []

    for _, root in tree:
        variant_archive = VariationArchiveParser(root, archive_folder)
        data = variant_archive.parse()
        root.clear()

        try:
            data = clinvar_vcf_check(data, clinvar_vcf)
        except IncompatibleDataError as e:
            logging.debug("Incompatible data: {}".format(e.message))
            continue

        added_vcf_lines = get_vcf_lines(data)

        if not added_vcf_lines and data["variant_id"] in clinvar_vcf:
            logging.error(
                "No vcf lines produced for variant {}, even though variant is in clinvar vcf".format(data["variant_id"])
            )
        elif added_vcf_lines and data["variant_id"] not in clinvar_vcf:
            logging.debug("Variant {} not in clinvar VCF, but included in output".format(data["variant_id"]))

        vcf_lines += added_vcf_lines

    return vcf_lines


def entrez_fetch_variation_data(ids):
    url = "https://www.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    data = "db=clinvar&rettype=vcv&is_variationid&id={}".format(",".join(ids))
    if API_KEY is not None:
        data += "&api_key={}".format(API_KEY)
    r = urllib2.urlopen(url, data=data)
    xml = r.read()
    return xml


def read_from_archive(ids, archive_file):
    # Read xml from archive
    xml = "<ClinVarResult-Set>\n"
    with tarfile.open(archive_file, "r") as archive:
        archive_root = archive_file.strip(".tar.gz")
        for variant_id in ids:
            member = os.path.join(archive_root, variant_id[:4], variant_id + ".xml")
            try:
                variant_xml = archive.extractfile(member)
            except KeyError:
                continue

            xml += variant_xml.read()

    xml += "</ClinVarResult-Set>"
    return xml


def execute_batch(ids, clinvar_vcf, write_archive, archive_file):
    """Wrapper for running a forked job. Used to get properly formatted exceptions from child process in main process."""
    # Errors that will trigger a retry

    n = 0
    # Set timeout of 60 seconds (after this, a TimeoutError will be raised)
    signal.alarm(60)
    while True:
        try:
            if archive_file:
                xml = read_from_archive(ids, archive_file)
            else:
                xml = entrez_fetch_variation_data(ids)
            return xml_to_vcf(xml, clinvar_vcf, write_archive)
        except Exception as e:
            logging.error("Exception in {}: {}".format(multiprocessing.current_process().name, str(e)))
            if type(e) in RETRY_ERRORS and n < MAX_RETRIES:
                logging.warning("{}. Retrying. ({} retries)".format(str(e), n))
                n += 1
                continue
            else:
                raise Exception("".join(traceback.format_exception(*sys.exc_info())))
        finally:
            # Reset alarm, so that no TimeoutError will be raised
            signal.alarm(0)


def parse_clinvar_file(vcf_file, archive_folder):
    """
    Fetch positions (chrom, pos, ref, alt) and (clinical significance, review status) from clinvar vcf.
    Returns a dictionary {variant_id: {"position": (chrom, pos, ref, alt), "clnsig": <clinical significance>, "revstat": <review status>}}
    """
    clinvar_vcf = dict()

    # Write clinvar file to archive. If archive_folder not given, just dump output to /dev/null
    if not archive_folder:
        archive_filename = os.devnull
    else:
        archive_filename = os.path.join(archive_folder, "clinvar.vcf")

    with open_file(vcf_file) as f, open(archive_filename, "w") as archive_file:
        for l in f:
            archive_file.write(l)
            if l.startswith("#"):
                continue

            chrom, pos, variant_id, ref, alt, _, _, info = l.strip().split("\t")
            assert variant_id not in clinvar_vcf
            # Skip non-variants
            if alt == ".":
                continue

            try:
                revstat = re.match(".*CLNREVSTAT=([^;]+).*", info).groups(1)[0].replace("_", " ")
            except AttributeError as e:
                revstat = "N/A"

            try:
                clnsig = re.match(".*CLNSIG=([^;]+).*", info).groups(1)[0].replace("_", " ")
            except AttributeError as e:
                clnsig = "N/A"

            clinvar_vcf[variant_id] = {"position": (chrom, pos, ref, alt), "clnsig": clnsig, "revstat": revstat}

    assert len(set([v["position"] for v in clinvar_vcf.values()])) == len(
        clinvar_vcf
    ), "Some positions in the clinvar vcf have multiple variant ids associated with it"
    return clinvar_vcf


def writer(outputfile, data, mode="a"):
    num_lines = 0
    with open(outputfile, mode) as f:
        for line in data:
            if not line.endswith("\n"):
                line += "\n"
            f.write(line)
            num_lines += 1
    logging.info("Wrote {} lines to {}".format(num_lines, outputfile))


def write_header(outputfile):
    # Write header of output file
    data = [
        "##fileformat=VCFv4.2",
        "##fileDate={}".format(TODAY),
        '##ID=<Description="ClinVar Variation ID">',
        '##INFO=<ID=CLNREVSTAT,Number=.,Type=String,Description="ClinVar review status for the Variation ID">',
        '##INFO=<ID=CLNSIG,Number=.,Type=String,Description="Clinical significance for this single variant">',
        '##INFO=<ID=CLINVARJSON,Number=1,Type=String,Description="Base 16-encoded JSON representation of metadata associated with this variant. Read back as lambda x: json.loads(base64.b16decode(x))">',
        '##INFO=<ID=VARIATION_ID,Number=1,Type=String,Description="The ClinVar variation ID">',
        '##INFO=<ID=VARIATION_TYPE,Number=1,Type=String,Description="Reported variation type">',
        '##INFO=<ID=WARN_FAILED_TO_CALCULATE_POSITION,Number=0,Type=Flag,Description="Failed to calculate position from xml data, using clinvar vcf position">',
        '##INFO=<ID=WARN_VARIANT_ID_NOT_IN_CLINVAR_VCF,Number=0,Type=Flag,Description="Variant id not in clinvar vcf">',
        '##INFO=<ID=WARN_MULTIPLE_POSITIONS,Number=0,Type=Flag,Description="Variant id is associated with multiple positions">',
        '##INFO=<ID=WARN_CLINVAR_VCF_CLNSIG_REVSTAT_MISMATCH,Number=.,Type=String,Description="Clinvar vcf reports a different clinsig and/or revstat. Formatted as clnsig:revstat">',
        '##INFO=<ID=WARN_CALCULATED_POSITION_MISMATCH,Number=.,Type=String,Description="Calculated a position different than clinvar vcf. Shows calculated positions as chr:pos:ref/alt. Used clinvar vcf position instead">',
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
    ]
    writer(outputfile, data, mode="w")


def print_summary(vcf_file, clinvar_vcf):
    "Print a summary of the generated file, and compare it to the NCBI provided clinvar vcf"
    total_warning_count = 0
    variant_count = 0
    variant_ids = set()
    positions = defaultdict(int)
    warnings = dict()
    with open(vcf_file, "r") as f:
        for l in f:
            if l.startswith("##INFO"):
                if "WARN" in l:
                    warnings[re.findall(".*?(WARN[^,]*)", l)[0]] = 0
            if l.startswith("#"):
                continue
            for w in warnings:
                if w in l:
                    warnings[w] += 1
            if "WARN" in l:
                total_warning_count += 1
            chrom, pos, variant_id, ref, alt = l.split("\t")[:5]
            position = (chrom, pos, ref, alt)
            positions[position] += 1

            variant_count += 1
            variant_ids.add(variant_id)
    num_variant_ids = len(variant_ids)

    summary = "\n".join(
        [
            "Output summary: ",
            "-- Number of variants: {}".format(variant_count),
            "-- Number of ClinVar variation ids: {}".format(num_variant_ids),
            "-- Number of variants with warnings: {}".format(total_warning_count),
            "-- Number of variants in output not in official ClinVar VCF: {}".format(
                len(set(variant_ids) - set(clinvar_vcf.keys()))
            ),
            "-- Variants in official ClinVar VCF not in output: {}".format(set(clinvar_vcf.keys()) - set(variant_ids)),
            "-- Number of duplicated positions: {}".format(len([v for v in positions.values() if v > 1])),
        ]
        + ["-- Number of variants with {}: {}".format(w, c) for w, c in warnings.items()]
    )
    logging.info(summary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--output", type=str, required=True, help="Output VCF-file to write clinvar database to")
    parser.add_argument(
        "-ivcf",
        "--clinvar_vcf",
        type=str,
        default="ftp://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh37/clinvar.vcf.gz",
        help="Input VCF-file (.vcf or .vcf.gz) containing clinvar variants parsed to vcf (incomplete)",
    )
    parser.add_argument(
        "-N",
        "--batch_size",
        type=int,
        default=1000,
        help="Number of variant ids to read in batch. If set too high, the API calls to entrez could fail.",
    )
    parser.add_argument("-np", "--num_processes", type=int, default=1, help="Number of processes to run in parallel")
    parser.add_argument(
        "-na",
        "--no-archive",
        action="store_true",
        help="If true, will not archive all fetched XMLs and input for debugging and auditing purposes. Otherwise, will create a clinvar-raw-{DATE}.tar.gz-file",
    )
    parser.add_argument("--archive-file", type=str, help="Path to archive to read from")
    parser.add_argument("--debug", default=False, action="store_true", help="Print debug messages")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    else:
        logging.basicConfig(stream=sys.stdout, level=logging.INFO)

    if API_KEY is None:
        logging.warning(
            "API key for the entrez API is not set. This will limit the queries to 3 per second (instead of 10 per sec)."
        )

    # Check whether to read from archive or not
    archive = args.archive_file
    write_archive = not args.no_archive
    if archive:
        if write_archive:
            logging.info("Reading from archive. Will not write back to archive.")
        write_archive = False
        with tarfile.open(archive, "r") as f:
            clinvar_vcf_file = os.path.join(archive.strip("tar.gz"), "clinvar.vcf")
            f.extract(clinvar_vcf_file)
    else:
        clinvar_vcf_file = args.clinvar_vcf

    outputfile = args.output
    batch_size = args.batch_size
    num_processes = args.num_processes

    if write_archive:
        archive_folder = os.path.join("clinvar_raw_{}".format(TODAY.replace("/", "-")))
        if not os.path.isdir(archive_folder):
            os.mkdir(archive_folder)
        else:
            raise RuntimeError("Archive folder {} exists. Aborting.".format(archive_folder))
    else:
        archive_folder = None

    clinvar_vcf = parse_clinvar_file(clinvar_vcf_file, archive_folder)

    # There seems to be no definitive source for variation ids for clinvar. However, they are sequential.
    # Find the maximum id in the clinvar vcf, and add substantial padding to this, and query for all variation ids
    # from 0 to max_variant_id + padding. If clinvar doesn't have an entry for the variation id, it will not be returned
    # in the results.
    max_variant_id = max(int(x) for x in clinvar_vcf)
    padding = 50000
    variant_ids = [str(i) for i in range(max_variant_id + padding)]

    num_batches = len(variant_ids) / batch_size + int(len(variant_ids) % batch_size >= 1)
    logging.info("Submitting {} jobs of length {}".format(num_batches, batch_size))

    write_header(outputfile)

    # Submit jobs in batches of batch_size. If num_processes > 1, run them in parallel using multiprocessing Pool
    # Pool for downloading xmls using NCBIs Entrez API in parallel.
    # Increasing the size of the pool could hit the rate limit of the Entrez API.
    # Furthermore, this is not the bottleneck, as parsing the results in the main thread is the

    if num_processes == 1:
        batch_number = 0
        logging.info("Running in serial.")
        while variant_ids:
            ids, variant_ids = (variant_ids[:batch_size], variant_ids[batch_size:])
            batch_number += 1
            data = execute_batch(ids, clinvar_vcf, archive_folder, archive)
            num_lines = writer(outputfile, data, batch_number=batch_number)
            logging.info(
                "Batch {} of {} completed. Wrote {} variants to vcf.".format(batch_number, num_batches, num_lines)
            )
    else:
        WORKERPOOL = Pool(processes=num_processes)
        jobs = []
        batch_number = 0

        while variant_ids:
            batch_number += 1
            ids, variant_ids = (variant_ids[:batch_size], variant_ids[batch_size:])
            job = WORKERPOOL.apply_async(
                execute_batch, (ids, clinvar_vcf, archive_folder, archive), callback=lambda x: writer(outputfile, x)
            )
            jobs.append(job)

        WORKERPOOL.close()
        processed = set()

        for i, job in enumerate(jobs):
            try:
                data = job.get()
                logging.info("Batch {} of {} completed.".format(i + 1, num_batches))
                processed.add(i)
            except Exception as e:
                WORKERPOOL.close()
                WORKERPOOL.terminate()
                logging.error("Job {} failed with exception:".format(i + 1))
                raise
        # This should be "instantaneous", since all jobs are processed. If it takes longer,
        # it indicates that some job(s) did not finish.
        assert processed == set(range(len(jobs))), "Not all jobs processed"
        signal.alarm(60)
        WORKERPOOL.join()
        signal.alarm(0)

    if write_archive:
        subprocess.call("tar -cf {0}.tar.gz {0}".format(archive_folder), shell=True)
        subprocess.call("rm -rf {}".format(archive_folder), shell=True)

    # Postprocessing
    vcf_sort(outputfile)
    vcf_validator(outputfile)
    print_summary(outputfile, clinvar_vcf)

    bgzip(outputfile)
    tabix(outputfile + ".gz")

    logging.info("Completed")


if __name__ == "__main__":
    main()
