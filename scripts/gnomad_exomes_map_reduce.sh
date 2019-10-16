#!/bin/bash

# gnomAD exomes is downloaded as one single file with all chromosomes
# parallel per chromosome processing due to large memory required by vt-rminfo
#  remove histogram fields and VEP annotation (CSQ field)
#  decomepose and normalize by vt
# merge by appending instead of vt-concatenate due to large memory required
# bgzip
# tabix

# get path to vcpipe-bin
# get gnomAD revision

set -eu -o pipefail

USAGE='\nUSAGE:\n---------------------------\ngnomad_exome_map_reduce.sh -b ~/vcpipe-bin -f ~/vcpipe-bundle/genomic/gatkBundle_2.5/human_g1k_v37_decoy_vt_0.5/human_g1k_v37_decoy.fasta -r 2.0.1\n---------------------------\n\nCAUTION:\n---------------------------\nUse the reference genome in vt specific subdir, e.g. human_g1k_v37_decoy_vt_0.5\n---------------------------\n'

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

if [ -z "$GNOMADVERSION" ]
then
  echo Error! gnomAD revision missing.
  printf "%b" "$USAGE"
  exit 1
fi

# processing each chromosome in parallel due to large memory usage and long time taken by vt
for i in {1..22} X Y
do
  (
      "${VCPIPEBIN}"/bin/tabix -p vcf -h gnomad.exomes.r"${GNOMADVERSION}".sites.vcf.bgz "$i" \
          | "${VCPIPEBIN}"/bin/vt rminfo - -t GQ_HIST_ALT,DP_HIST_ALT,AB_HIST_ALT,GQ_HIST_ALL,DP_HIST_ALL,AB_HIST_ALL,CSQ \
          | "${VCPIPEBIN}"/bin/vt decompose -s - \
          | "${VCPIPEBIN}"/bin/vt normalize -r "${REFERENCE}" -n - \
          > gnomad.exomes.r"${GNOMADVERSION}".chr"$i".norm.vcf
  ) &
done
wait

# merge by appending instead of vt-concatenate due to large memory required by vt-concatenate
mv gnomad.exomes.r"${GNOMADVERSION}".chr1.norm.vcf gnomad.exomes.r"${GNOMADVERSION}".norm.vcf
for i in {2..22} X Y
do
  "${VCPIPEBIN}"/bin/vt view gnomad.exomes.r"${GNOMADVERSION}".chr"$i".norm.vcf >> gnomad.exomes.r"${GNOMADVERSION}".norm.vcf
  rm gnomad.exomes.r"${GNOMADVERSION}".chr"$i".norm.vcf
done

#bgzip
"${VCPIPEBIN}"/bin/bgzip gnomad.exomes.r"${GNOMADVERSION}".norm.vcf

#index
"${VCPIPEBIN}"/bin/tabix -p vcf gnomad.exomes.r"${GNOMADVERSION}".norm.vcf.gz

#cleanup
rm gnomad.exomes.r"${GNOMADVERSION}".sites.vcf.bgz
rm gnomad.exomes.r"${GNOMADVERSION}".sites.vcf.bgz.tbi
