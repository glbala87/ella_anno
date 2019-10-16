#!/bin/bash

# gnomAD genomes is downloaded per chromosome
# remove histogram fields
# remove VEP annotation (CSQ field)
# slice by MasterGenePanelExons.list
# decomepose and normalize by vt

set -eu -o pipefail

USAGE='\nUSAGE:\ngnomad_genome_reduce.sh -b ~/vcpipe-bin -f ~/vcpipe-bundle/genomic/gatkBundle_2.5/human_g1k_v37_decoy_vt_0.5/human_g1k_v37_decoy.fasta -m ~/vcpipe-bundle/funcAnnot/refseq/MasterGenePanelExons.list -r 2.0.1\n\nCAUTION:\nUse the reference genome in vt specific subdir, e.g. human_g1k_v37_decoy_vt_0.5\n'

while [ $# -gt 1 ]
do
  key="$1"
  case "$key" in
    -b|--vcpipe-bin)
      VCPIPEBIN="$2"
      shift 2
      ;;
    -f|--reference-genome)
      REFERENCE="$2"
      shift 2
      ;;
    -m|--master-panel)
      PANEl="$2"
      shift 2
      ;;
    -r|--gnomad-revision)
      GNOMADVERSION="$2"
       shift 2
       ;;
    *)
      break
      ;;
  esac
done

if [ -z "$VCPIPEBIN" ]
then
  echo Error! path to vcpipe-bin missing.
  printf "%b" "$USAGE"
  exit 1
fi

if ! [ -d "$VCPIPEBIN" ]
then
  echo Error! path to vcpipe-bin "'${VCPIPEBIN}'" not found
  printf "%b" "$USAGE"
  exit 1
fi

if [ -z "$REFERENCE" ]
then
  echo Error! path to reference genome missing.
  printf "%b" "$USAGE"
  exit 1
fi

if ! [ -f "$REFERENCE" ]
then
  echo Error! wrong reference genome "'$REFERENCE'"
  printf "%b" "$USAGE"
  exit 1
fi

if [ -z "$PANEl" ]
then
  echo Error! path to master panel missing.
  printf "%b" "$USAGE"
  exit 1
fi

if ! [ -f "$PANEl" ]
then
  echo Error! wrong master panel "$PANEl"
  printf "%b" "$USAGE"
  exit 1
fi

if [ -z "$GNOMADVERSION" ]
then
  echo Error! gnomAD revision missing.
  printf "%b" "$USAGE"
  exit 1
fi

for i in {1..22} X
do
  (
      "${VCPIPEBIN}"/bin/vt rminfo gnomad.genomes.r"${GNOMADVERSION}".sites.chr"$i".vcf.bgz -t GQ_HIST_ALT,DP_HIST_ALT,AB_HIST_ALT,GQ_HIST_ALL,DP_HIST_ALL,AB_HIST_ALL,CSQ -I "${PANEl}" \
          | "${VCPIPEBIN}"/bin/vt decompose -s - \
          | "${VCPIPEBIN}"/bin/vt normalize -r "${REFERENCE}" -n - \
          > gnomad.genomes.r"${GNOMADVERSION}".sites.chr"$i".sliced.norm.vcf
  )&
done
wait

# merge by appending instead of vt-concatenate due to large memory required by vt-concatenate
mv gnomad.genomes.r"${GNOMADVERSION}".sites.chr1.sliced.norm.vcf gnomad.genomes.r"${GNOMADVERSION}".sliced.norm.vcf
for i in {2..22} X
do
  "${VCPIPEBIN}"/bin/vt view gnomad.genomes.r"${GNOMADVERSION}".sites.chr"$i".sliced.norm.vcf >> gnomad.genomes.r"${GNOMADVERSION}".sliced.norm.vcf
  rm gnomad.genomes.r"${GNOMADVERSION}".sites.chr"$i".sliced.norm.vcf
done

# bgzip
"${VCPIPEBIN}"/bin/bgzip gnomad.genomes.r"${GNOMADVERSION}".sliced.norm.vcf

# tabix
"${VCPIPEBIN}"/bin/tabix -p vcf gnomad.genomes.r"${GNOMADVERSION}".sliced.norm.vcf.gz

#cleanup
for i in {1..22} X
do
  rm gnomad.genomes.r"${GNOMADVERSION}".sites.chr"$i".vcf.bgz
  rm gnomad.genomes.r"${GNOMADVERSION}".sites.chr"$i".vcf.bgz.tbi
done
