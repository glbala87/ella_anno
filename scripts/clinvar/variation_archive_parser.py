import os
from collections import defaultdict
from lxml import etree

submitter_map = dict()
submitter_map["Illumina Clinical Services Laboratory,Illumina"] = "Illumina"
submitter_map["Evidence-based Network for the Interpretation of Germline Mutant Alleles (ENIGMA)"] = "ENIGMA"
submitter_map["Breast Cancer Information Core (BIC) (BRCA2)"] = "BIC (BRCA2)"
submitter_map["Breast Cancer Information Core (BIC) (BRCA1)"] = "BIC (BRCA1)"
submitter_map["Consortium of Investigators of Modifiers of BRCA1/2 (CIMBA), c/o University of Cambridge"] = "CIMBA"
submitter_map["Sharing Clinical Reports Project (SCRP)"] = "SCRP"
submitter_map["Emory Genetics Laboratory,Emory University"] = "Emory Genetics Lab"
submitter_map["Counsyl,"] = "Counsyl"
submitter_map[
    "Laboratory for Molecular Medicine,Partners HealthCare Personalized Medicine"
] = "Laboratory for Molecular Medicine"
submitter_map["Genetic Services Laboratory, University of Chicago"] = "Genetic Services Laboratory, Chicago"
submitter_map["Tuberous sclerosis database (TSC2)"] = "TSC2"
submitter_map["LDLR-LOVD, British Heart Foundation"] = "LDLR-LOVD"
submitter_map["ARUP Institute,ARUP Laboratories"] = "ARUP"


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


class VariationArchiveParser:
    """
    Class for parsing required data from the ClinVar XML with tag <VariationArchive>.
    See e.g. https://www.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=clinvar&rettype=vcv&is_variationid&id=9 for example.
    """

    def __init__(self, root, archive_folder=None):
        assert root.tag == "VariationArchive"
        self.root = root
        self.archive_folder = archive_folder
        if self.archive_folder:
            self._write_archive()
        self.position_warnings = defaultdict(list)
        self.variation_warnings = []

    @property
    def variant_id(self):
        if not hasattr(self, "_variant_id"):
            self._variant_id = scalar_xpath(self.root, "@VariationID", require=True)
        return self._variant_id

    @property
    def variation_type(self):
        return scalar_xpath(self.root, "@VariationType", require=True)

    @property
    def alleles(self):
        return self.root.xpath("./InterpretedRecord/SimpleAllele")

    def _write_archive(self):
        "Write XML to archive <self.archive_folder>/<variant_id>[:4]/<variant_id>.xml"
        archive_subdir = os.path.join(self.archive_folder, self.variant_id[:4])
        if not os.path.isdir(archive_subdir):
            try:
                os.mkdir(os.path.join(archive_subdir))
            except OSError:
                assert os.path.isdir(archive_subdir)
        with open(os.path.join(self.archive_folder, self.variant_id[:4], self.variant_id + ".xml"), "w") as f:
            f.write(etree.tostring(self.root, encoding="utf-8", pretty_print=False))

    @property
    def positions(self):
        """
        Positions in the XML is normally defined with the attributes positionVCF, referenceAlleleVCF, alternateAlleleVCF.
        Rather than attempting to fix the cases where this is not the case, we ignore them.
        (Note however, that they are included with position from the clinvar vcf release if the variant exist there)
        """
        alleles = self.alleles
        xml_positions = set()
        if not alleles:
            return xml_positions
        else:
            assert len(alleles) == 1
            allele = alleles[0]
            seq_locs = allele.xpath("./Location/SequenceLocation[@Assembly='GRCh37']")
            for seq_loc in seq_locs:
                chrom = scalar_xpath(seq_loc, "@Chr", smart_strings=False)
                position = scalar_xpath(seq_loc, "@positionVCF", smart_strings=False)
                ref = scalar_xpath(seq_loc, "@referenceAlleleVCF", smart_strings=False)
                alt = scalar_xpath(seq_loc, "@alternateAlleleVCF", smart_strings=False)

                # Not well defined
                if any([x is None for x in [chrom, position, ref, alt]]):
                    continue
                xml_positions.add((chrom, position, ref, alt))
        return xml_positions

    @property
    def review_status(self):
        return scalar_xpath(
            self.root, "./*[self::IncludedRecord | self::InterpretedRecord]/ReviewStatus/text()", require=True
        )

    @property
    def clinical_significance(self):
        # Not currently used in CLINVARJSON. TODO: Update schema in ELLA
        clnsig = scalar_xpath(
            self.root,
            "./*[self::IncludedRecord | self::InterpretedRecord]/Interpretations/Interpretation[@Type='Clinical significance']/Description/text()",
            require=True,
        )
        # If it's an included record, there is no interpretation for the variant
        if clnsig == "no interpretation for the single variant":
            clnsig = "N/A"
        return clnsig

    @property
    def submissions(self):
        "Loop over submissions in the XML, and extract required information"
        rcvs = dict()
        submitters = self.root.xpath(".//ClinicalAssertionList//*[ClinVarAccession[@Accession][@SubmitterName]]")
        for scv in submitters:
            scv_id = scalar_xpath(scv, "./ClinVarAccession/@Accession", require=True)
            submitter_name = scalar_xpath(scv, "./ClinVarAccession/@SubmitterName", require=True)
            submitter_name = submitter_map.get(submitter_name, submitter_name)
            traitnames = scv.xpath("./TraitSet/Trait/Name/ElementValue/text()")
            scv_clnrevstat = scalar_xpath(scv, "./ReviewStatus/text()", require=True)
            scv_clnsig = scalar_xpath(scv, "./Interpretation/Description/text()")
            if not scv_clnsig:
                scv_clnsig = "not provided"
            last_evaluated = scalar_xpath(scv, "./Interpretation/@DateLastEvaluated")
            if last_evaluated is None:
                last_evaluated = "N/A"

            # TODO: We use this terrible structure for now, to keep backward compatibility.
            # Change when annotation is versioned in ELLA
            rcvs[scv_id] = {
                "traitnames": traitnames,
                "last_evaluated": [last_evaluated],
                "submitter": [submitter_name],
                "clinical_significance_descr": [scv_clnsig],
                "clinical_significance_status": [scv_clnrevstat],
                "variant_id": [self.variant_id],
            }
        return rcvs

    @property
    def pubmed_ids(self):
        """
        Pubmed IDs shown on website. Refer to https://www.ncbi.nlm.nih.gov/clinvar/docs/variation_report/#citations:
        "Citations can be provided in several places in submissions; this table includes all citations except for those
        submitted on the condition and citations submitted as assertion criteria."
        """
        return list(
            set(
                self.root.xpath(
                    ".//Citation[not(ancestor::Trait)][not(ancestor::AttributeSet/Attribute[@Type='AssertionMethod'])]/ID[@Source='PubMed']/text()"
                )
            )
        )

    def parse(self):
        "Parse and return data dictionary"
        data = {
            "positions": self.positions,
            "clnsig": self.clinical_significance,
            "revstat": self.review_status,
            "variation_warnings": self.variation_warnings,
            "position_warnings": self.position_warnings,
            "variation_type": self.variation_type,
            "variant_id": self.variant_id,
            "pubmed_ids": self.pubmed_ids,
            "submissions": self.submissions,
        }

        return data
