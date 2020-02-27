#!/usr/bin/env python

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
- pyfaidx
- jsonschema

Requirements (command line tools):
- vt
- vcftools (vcf-validator, vcf-sort)
- bgzip

"""

import urllib2
import httplib
import multiprocessing
import time
import re
import os
import json
import base64
import argparse
import gzip
import tempfile
import subprocess
import traceback
import sys
import tarfile
import logging
import datetime
from collections import defaultdict
from multiprocessing.pool import Pool
from cStringIO import StringIO
from lxml import etree
from pyfaidx import Fasta

from get_vcf_positions import get_vcf_positions, scalar_xpath
from mappings import submitter_map

TODAY = datetime.datetime.today().strftime("%d/%m/%Y")
ARCHIVE_FOLDER = os.path.join("clinvar_raw_{}".format(TODAY.replace("/", "-")))


# API KEY for entrez utilities (https://ncbiinsights.ncbi.nlm.nih.gov/2017/11/02/new-api-keys-for-the-e-utilities/)
API_KEY = os.environ.get("ENTREZ_API_KEY")

# Max retries for the API calls
MAX_RETRIES = 10

# Container for possible translations of alt alleles.
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


def read_genome(filename):
    "Read genome data using pyfaidx.Fasta"
    genome = Fasta(filename, as_raw=True, rebuild=False)
    return genome


def process_results(xml, genome_file, archive=True):
    """
    Read all VariationReport tags and attempt to create one or more vcf lines from it. Return all vcf lines extracted from xml.
    """
    tree = etree.iterparse(StringIO(xml), tag="VariationReport", events=["end"])
    vcf_lines = []

    # NOTE: genome should not be shared, as reading it back is not thread safe
    # From this point, no forking will be done, so it's safe to read here
    genome = read_genome(genome_file)

    for _, root in tree:
        assert root.tag == "VariationReport"
        variant_id = scalar_xpath(root, "@VariationID", require=True)

        # Archive variant xml
        # E.g. for variant id 123456, write xml to ARCHIVE_FOLDER/1234/123456.xml
        if archive:
            archive_subdir = os.path.join(ARCHIVE_FOLDER, variant_id[:4])
            if not os.path.isdir(archive_subdir):
                try:
                    os.mkdir(os.path.join(archive_subdir))
                except OSError:
                    assert os.path.isdir(archive_subdir)
            with open(os.path.join(ARCHIVE_FOLDER, variant_id[:4], variant_id + ".xml"), "w") as f:
                f.write(etree.tostring(root, encoding="utf-8", pretty_print=False))

        variation_type = scalar_xpath(root, "@VariationType", require=True)
        alleles = root.xpath("./Allele")

        # Skip haplotypes/compound heterozygous variations, as these might consist of alleles that are submitted as standalone variations
        # Some haplotypes are reported with a single allele. These will be kept.
        if len(alleles) > 1 and variation_type in ["Haplotype", "Compound heterozygote", "Phase unknown", "Diplotype"]:
            continue

        vcf_positions_all_alleles = []
        position_warnings = defaultdict(list)

        for allele in root.iter(tag=("Allele")):
            try:
                vcf_positions = get_vcf_positions(genome, allele)
            except Exception as e:
                if variant_id in clinvar_vcf_positions:
                    clinvar_position = clinvar_vcf_positions[variant_id]
                    position_warnings[clinvar_position] += ["WARN_FAILED_TO_CALCULATE_POSITION"]
                    vcf_positions = [clinvar_vcf_positions[variant_id]]
                    logging.debug(
                        "Failed to calculate position for variant id {}. Using clinvar vcf position".format(variant_id)
                    )
                else:
                    logging.debug("Failed to calculate position for variant id {}. Skipping.".format(variant_id))
                    continue

            if variant_id in clinvar_vcf_positions:
                if clinvar_vcf_positions[variant_id] not in vcf_positions:
                    logging.debug(
                        "Position does not match clinvar position for variant id {}:\n".format(variant_id)
                        + "-- Clinvar: {}\n".format(clinvar_vcf_positions[variant_id])
                        + "-- Calculated: {}\n".format(vcf_positions)
                        + "-- Using clinvar vcf position"
                    )
                    clinvar_position = clinvar_vcf_positions[variant_id]
                    position_warnings[clinvar_position] += [
                        "WARN_CALCULATED_POSITION_MISMATCH=" + ",".join("{}:{}:{}/{}".format(*k) for k in vcf_positions)
                    ]
                    vcf_positions = [clinvar_position]

            vcf_positions_all_alleles += vcf_positions

        vcf_positions_all_alleles = set(vcf_positions_all_alleles)

        # Convert positions where alt is in ALT_TRANSLATIONS
        # E.g. where for key ("1", 123, "A", "Y"), drop position in favour of ("1", 123, "A", "C") and ("1", 123, "A", "T")
        corrected_positions_all = []
        for chrom, pos, ref, alt in vcf_positions_all_alleles:
            if alt not in ALT_TRANSLATIONS:
                corrected_positions_all.append((chrom, pos, ref, alt))
            else:
                corrected_positions = [
                    (chrom, pos, ref, new_alt) for new_alt in ALT_TRANSLATIONS[alt] if new_alt != ref
                ]
                if (chrom, pos, ref, alt) in position_warnings:
                    position_warning = position_warnings.pop((chrom, pos, ref, alt))
                    for corr_position in corrected_positions:
                        position_warnings[corr_position] = position_warning
                for corr_position in corrected_positions:
                    position_warnings[corr_position] += ["WARN_TRANSLATED_ALT={}:{}:{}/{}".format(chrom, pos, ref, alt)]
                logging.debug(
                    "{}: Variant id {}: corrected {} to {}".format(
                        multiprocessing.process.current_process().name,
                        variant_id,
                        (chrom, pos, ref, alt),
                        corrected_positions,
                    )
                )
                corrected_positions_all += corrected_positions

        vcf_positions_all_alleles = set(corrected_positions_all)

        if not vcf_positions_all_alleles:
            continue

        variation_warnings = []
        if len(vcf_positions_all_alleles) > 1:
            logging.debug(
                "Variant id {} has multiple positions associated with it: {}".format(
                    variant_id, vcf_positions_all_alleles
                )
            )
            variation_warnings.append("WARN_MULTIPLE_POSITIONS")

        # Fetch review status (translatable to number of stars) and clinical significance (e.g. Pathogenic or Benign)
        revstat = scalar_xpath(
            root,
            "./ObservationList/Observation[@VariationID='{}']/ReviewStatus/text()".format(variant_id),
            require=True,
        )
        clnsig = scalar_xpath(
            root,
            "./ObservationList/Observation[@VariationID='{}']/ClinicalSignificance/Description/text()".format(
                variant_id
            ),
            require=True,
        )

        if variant_id in clinvar_vcf_clnsigs_and_revstat:
            if clinvar_vcf_clnsigs_and_revstat[variant_id] != (clnsig, revstat):
                variation_warnings.append(
                    "WARN_CLINVAR_VCF_CLNSIG_REVSTAT_MISMATCH={}:{}".format(
                        *[s.replace(" ", "_") for s in clinvar_vcf_clnsigs_and_revstat[variant_id]]
                    )
                )
                logging.debug(
                    "clnsig and revstat not matching clinvar vcf for variant id {}:\n".format(variant_id)
                    + "-- ClinVar VCF: {}\n".format(clinvar_vcf_clnsigs_and_revstat[variant_id])
                    + "-- Fetched from XML: {}".format((clnsig, revstat))
                )

        if variant_id not in clinvar_vcf_positions:
            logging.debug("Variant id {} not in clinvar VCF".format(variant_id))
            variation_warnings.append("WARN_VARIANT_ID_NOT_IN_CLINVAR_VCF")

        # Fetch interesting data from SCVs
        scvs = []
        rcvs = dict()
        submitters = root.xpath(".//ClinicalAssertionList//*[@SubmitterName][@Accession]")
        for scv in submitters:
            scv_id = scalar_xpath(scv, "@Accession", require=True)
            submitter_name = scalar_xpath(scv, "@SubmitterName", require=True)
            submitter_name = submitter_map.get(submitter_name, submitter_name)
            traitnames = scv.xpath("./PhenotypeList/Phenotype/@Name")
            scv_clnrevstat = scalar_xpath(scv, "./ReviewStatus/text()", require=True)
            scv_clnsig = scalar_xpath(scv, "./ClinicalSignificance/Description/text()", require=True)
            last_evaluated = scalar_xpath(scv, "./ClinicalSignificance/@DateLastEvaluated")
            if last_evaluated is None:
                last_evaluated = "N/A"

            # TODO: We use this terrible structure for now, to keep backward compatibility.
            # Change when annotation is versioned in ella
            rcvs[scv_id] = {
                "traitnames": traitnames,
                "last_evaluated": [last_evaluated],
                "submitter": [submitter_name],
                "clinical_significance_descr": [scv_clnsig],
                "clinical_significance_status": [scv_clnrevstat],
                "variant_id": [variant_id],
            }
            # scvs.append(
            #     {
            #         "scv_id": scv_id,
            #         "clnsig": scv_clnsig,
            #         "clnrevstat": scv_clnrevstat,
            #         "last_evaluated": last_evaluated,
            #         "phenotypes": traitnames,
            #         "submitter": submitter_name,
            #         "origin": scv.tag.lower(),
            #     }
            # )

        # Fetch pubmeds
        pubmed_ids = list(set(root.xpath(".//Citation/ID[@Source='PubMed']/text()")))

        # TODO: Change when annotation is versioned in ella
        data = {
            "variant_id": int(variant_id),
            "variant_description": revstat,
            "pubmeds": pubmed_ids,
            "rcvs": rcvs,
            # "date_retrieved": TODAY,
            # "variation_type": variation_type,
        }

        CLINVAR_V1_SCHEMA = {
            "definitions": {
                "rcv": {
                    "$id": "#/definitions/rcv",
                    "type": "object",
                    "required": [
                        "traitnames",
                        "clinical_significance_descr",
                        "variant_id",
                        "submitter",
                        "last_evaluated",
                    ],
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

        import jsonschema

        jsonschema.validate(data, CLINVAR_V1_SCHEMA)

        # data = {
        #     "variant_id": variant_id,
        #     "review_status": revstat,
        #     "clinical_significance": clnsig,
        #     "pubmeds": pubmed_ids,
        #     "scvs": scvs,
        #     # "date_retrieved": TODAY,
        #     # "variation_type": variation_type,
        # }
        # print json.dumps(data, indent=4)

        info = base64.b16encode(json.dumps(data, separators=(",", ":")))

        for chrom, position, ref, alt in vcf_positions_all_alleles:
            if ref == alt:
                # Skip non-variants
                logging.debug("Non-variant found {} (variant id: {})".format((chrom, position, ref, alt), variant_id))
                continue
            elif (len(ref) > 1000 or len(alt) > 1000) and variant_id not in clinvar_vcf_positions:
                # Skip long variants (if not in clinvar vcf)
                logging.debug(
                    "Too long variant {} (variant id: {})".format(
                        (chrom, position, "[{}]".format(len(ref)), "[{}]".format(len(alt))), variant_id
                    )
                )
                continue
            elif not (set(ref).issubset(set("ACGT")) and set(alt).issubset(set("ACGT"))):
                # Skip variants where ref or alt is not well defined
                logging.debug("Variant not well defined {}. Variant id: {}".format((chrom, pos, ref, alt), variant_id))
                continue

            vcf_lines.append(
                "{chrom}\t{pos}\t{variant_id}\t{ref}\t{alt}\t5000\tPASS\tVARIATION_TYPE={variation_type};VARIATION_ID={variant_id};CLNSIG={clnsig};CLNREVSTAT={revstat};CLINVARJSON={info}{variation_warnings}{position_warnings}".format(
                    chrom=chrom,
                    pos=position,
                    variant_id=variant_id,
                    ref=ref,
                    alt=alt,
                    variation_type=variation_type.replace(" ", "_"),
                    clnsig=clnsig.replace(" ", "_"),
                    revstat=revstat.replace(" ", "_"),
                    info=info,
                    variation_warnings="" if not variation_warnings else ";" + ";".join(variation_warnings),
                    position_warnings=""
                    if not position_warnings[(chrom, position, ref, alt)]
                    else ";" + ";".join(position_warnings[(chrom, position, ref, alt)]),
                )
            )

    return vcf_lines


def fetch_variation_data(ids, archive_file=None):
    """
    Fetch variation ids, either from archive file or entrez' eutils. To see example of returned xml, visit
    https://www.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=clinvar&rettype=variation&id=1333,568123
    """
    if archive_file:
        # Read xml from archive
        xml = "<ClinVarResult-Set>\n"
        for variant_id in ids:
            filename = os.path.join(archive_file.replace(".tar.gz", ""), variant_id[:4], variant_id + ".xml")
            if os.path.isfile(filename):
                with open(filename, "r") as variant_xml:
                    xml += variant_xml.read()

        xml += "</ClinVarResult-Set>"
        return xml
    else:
        # Read xml from entrez' eutils
        url = "https://www.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        data = "db=clinvar&rettype=variation&id={}".format(",".join(ids))
        if API_KEY is not None:
            data += "&api_key={}".format(API_KEY)
        n = 0
        while n < MAX_RETRIES:
            try:
                r = urllib2.urlopen(url, data=data)
                xml = r.read()
                return xml
            except (urllib2.HTTPError, urllib2.URLError) as e:
                logging.warning("{}. Retrying. ({} retries)".format(str(e), n))
                n += 1
                time.sleep(1 * n)

        raise RuntimeError("Reached max retries for url: {}".format(url))


def run_job(ids, genome_file, write_archive, archive_file):
    """Wrapper for running a forked job. Used to get properly formatted exceptions from child process in main process."""
    retry_errs = [httplib.IncompleteRead]
    n = 0
    while n < MAX_RETRIES:
        try:
            xml = fetch_variation_data(ids, archive_file)
            return process_results(xml, genome_file, write_archive)
        except Exception as e:
            if type(e) in retry_errs:
                logging.warning("{}. Retrying. ({} retries)".format(str(e), n))
                n += 1
                continue
            raise Exception("".join(traceback.format_exception(*sys.exc_info())))


def parse_clinvar_file(vcf_file, archive=True):
    """
    Fetch positions (chrom, pos, ref, alt) and (clinical significance, review status) from clinvar vcf.
    Returns two dicts:
        vcf_positions = {variant_id: (chrom, pos, ref, alt)}
        clnsig_and_revstat = {variant_id: (clinical significance, review status)}
    """
    vcf_positions = dict()
    clnsig_and_revstat = dict()

    # Write clinvar file to archive. If not archive, just dump output to /dev/null
    if not archive:
        archive_filename = os.devnull
    else:
        archive_filename = os.path.join(ARCHIVE_FOLDER, "clinvar.vcf")

    with open_file(vcf_file) as f, open(archive_filename, "w") as archive_file:
        for l in f:
            archive_file.write(l)
            if l.startswith("#"):
                continue

            chrom, pos, variant_id, ref, alt, _, _, info = l.strip().split("\t")
            assert variant_id not in vcf_positions
            if alt == ".":
                alt = ref

            vcf_positions[variant_id] = (chrom, int(pos), ref, alt)

            assert variant_id not in clnsig_and_revstat
            try:
                revstat = re.match(".*CLNREVSTAT=([^;]+).*", info).groups(1)[0].replace("_", " ")
            except AttributeError as e:
                revstat = "N/A"

            try:
                clnsig = re.match(".*CLNSIG=([^;]+).*", info).groups(1)[0].replace("_", " ")
            except AttributeError as e:
                clnsig = "N/A"
            clnsig_and_revstat[variant_id] = (clnsig, revstat)

    return vcf_positions, clnsig_and_revstat


def open_file(inputfile):
    """Opens input file. Downloads with wget if applicable. Opens with gzip og open based on extension"""
    if inputfile.startswith("ftp") or inputfile.startswith("http"):
        logging.info("Downloading input file {}".format(inputfile))
        t1 = time.time()
        download_to = os.path.split(inputfile)[-1]
        os.system("wget {} -O {}".format(inputfile, download_to))
        inputfile = download_to
        t2 = time.time()
        logging.info("Downloaded inputfile " + inputfile + " in " + str(t2 - t1) + " seconds")

    if inputfile.endswith(".gz"):
        f = gzip.open(inputfile)
    else:
        f = open(inputfile)

    return f


def writer(outputfile, data, mode="a"):
    with open(outputfile, mode) as f:
        for l in data:
            if not l.endswith("\n"):
                l += "\n"
            f.write(l)


if __name__ == "__main__":
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
    parser.add_argument("-g", "--genome", type=str, required=True, help="Fasta file for genome (GRCh37)")
    parser.add_argument(
        "-a",
        "--archive",
        type=bool,
        default=True,
        help="If true, will archive all fetched XMLs and input for debugging and auditing purposes. Will create a clinvar-raw-{DATE}.tar.gz-file",
    )
    parser.add_argument("--archive_file", type=str, help="Path to archive to read from")
    parser.add_argument("--debug", default=False, action="store_true", help="Print debug messages")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    if API_KEY is None:
        logging.warning(
            "API key for the entrez API is not set. This will limit the queries to 3 per second (instead of 10 per sec)."
        )

    # Check whether to read from archive or not
    archive_file = args.archive_file
    write_archive = args.archive
    if archive_file:
        if write_archive:
            logging.info("Reading from archive. Will not write back to archive.")
        write_archive = False
        logging.info("Extracting archive {}".format(archive_file))
        with tarfile.open(archive_file, "r") as tar:
            tar.extractall()
        clinvar_vcf = os.path.join(archive_file.strip(".tar.gz"), "clinvar.vcf")
    else:
        clinvar_vcf = args.clinvar_vcf

    outputfile = args.output
    batch_size = args.batch_size
    num_processes = args.num_processes
    genome_file = args.genome

    if write_archive:
        if not os.path.isdir(ARCHIVE_FOLDER):
            os.mkdir(ARCHIVE_FOLDER)
        else:
            raise RuntimeError("Archive folder {} exists. Aborting.".format(ARCHIVE_FOLDER))

    clinvar_vcf_positions, clinvar_vcf_clnsigs_and_revstat = parse_clinvar_file(clinvar_vcf, archive=write_archive)

    # There seems to be no definitive source for variation ids for clinvar. However, they are sequential.
    # Find the maximum id in the clinvar vcf, and add substantial padding to this, and query for all variation ids
    # from 0 to max_variant_id + padding. If clinvar doesn't have an entry for the variation id, it will not be returned
    # in the results.
    max_variant_id = max(int(x) for x in clinvar_vcf_positions)
    padding = 50000
    variant_ids = [str(i) for i in range(max_variant_id + padding)]

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
        '##INFO=<ID=WARN_MULTIPLE_POSITIONS,Number=0,Type=Flag,Description="This variation has multiple positions associated with it.">',
        '##INFO=<ID=WARN_CLINVAR_VCF_CLNSIG_REVSTAT_MISMATCH,Number=.,Type=String,Description="Clinvar vcf reports a different clinsig and/or revstat. Formatted as clnsig:revstat">',
        '##INFO=<ID=WARN_CALCULATED_POSITION_MISMATCH,Number=.,Type=String,Description="Calculated a position different than clinvar vcf. Shows calculated positions as chr:pos:ref/alt. Used clinvar vcf position instead">',
        '##INFO=<ID=WARN_TRANSLATED_ALT,Number=1,Type=String,Description="Translated ALT column. Shows translated from as chr:pos:ref/alt">',
        "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO",
    ]
    writer(outputfile, data, mode="w")

    num_batches = len(variant_ids) / batch_size + int(len(variant_ids) % batch_size >= 1)
    logging.info("Submitting {} jobs of length {}".format(num_batches, batch_size))

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
            xml = fetch_variation_data(ids, archive_file)
            data = process_results(xml, genome_file, write_archive)
            writer(outputfile, data)
            logging.info("Batch {} of {} completed".format(batch_number, num_batches))
    else:
        WORKERPOOL = Pool(processes=num_processes, maxtasksperchild=1)
        jobs = []
        while variant_ids:
            ids, variant_ids = (variant_ids[:batch_size], variant_ids[batch_size:])
            p = WORKERPOOL.apply_async(run_job, (ids, genome_file, write_archive, archive_file))
            jobs.append(p)

        for i, job in enumerate(jobs):
            try:
                data = job.get()
                writer(outputfile, data)
                logging.info("Batch {} of {} completed".format(i + 1, num_batches))
            except Exception as e:
                WORKERPOOL.close()
                WORKERPOOL.terminate()
                logging.error("Job {} failed with exception:".format(i + 1))
                raise

    if write_archive:
        subprocess.call("tar -cf {0}.tar.gz {0}".format(ARCHIVE_FOLDER), shell=True)
        subprocess.call("rm -rf {}".format(ARCHIVE_FOLDER), shell=True)

    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.close()
    err1 = subprocess.call("vcf-sort -c {} > {}".format(outputfile, tmp.name), shell=True)
    err2 = subprocess.call("mv {} {}".format(tmp.name, outputfile), shell=True)
    if err1 != 0 or err2 != 0:
        logging.error("vcf-sort failed")
        exit(1)

    try:
        err = subprocess.call("vcf-validator -d {}".format(outputfile), shell=True)
    except Exception as e:
        logging.failed("Process completed, but vcf-validator failed (vcf-validator)")
        raise

    warnings = {
        "WARN_FAILED_TO_CALCULATE_POSITION": 0,
        "WARN_VARIANT_ID_NOT_IN_CLINVAR_VCF": 0,
        "WARN_CLINVAR_VCF_CLNSIG_REVSTAT_MISMATCH": 0,
        "WARN_CALCULATED_POSITION_MISMATCH": 0,
        "WARN_MULTIPLE_POSITIONS": 0,
        "WARN_TRANSLATED_ALT": 0,
    }
    total_warning_count = 0
    variant_count = 0
    variant_ids = set()
    with open(outputfile, "r") as f:
        for l in f:
            if l.startswith("#"):
                continue
            for w in warnings:
                if w in l:
                    warnings[w] += 1
            if "WARN" in l:
                total_warning_count += 1
            variant_count += 1
            variant_id = l.split("\t")[2]
            variant_ids.add(variant_id)
    num_variant_ids = len(variant_ids)
    summary = "\n".join(
        [
            "Output summary: ",
            "-- Number of variants: {}".format(variant_count),
            "-- Number of ClinVar variation ids: {}".format(num_variant_ids),
            "-- Number of variants with warnings: {}".format(total_warning_count),
        ]
        + ["-- Number of variants with {}: {}".format(w, c) for w, c in warnings.items()]
    )
    logging.info(summary)

    try:
        err = subprocess.call("bgzip -f {}".format(outputfile), shell=True)
    except Exception as e:
        logging.error("Process completed, but bgzip failed")
        raise

    try:
        err = subprocess.call("tabix -p vcf {}".format(outputfile + ".gz"), shell=True)
    except Exception as e:
        logging.error("Process completed, but tabix failed")
        raise

    logging.info("Completed")
