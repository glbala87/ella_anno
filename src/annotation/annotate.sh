#!/bin/bash -e

SOURCE_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

usage="Usage: `basename $0`

	-h|--help			        print this help text
	--vcf [vcf]			        input VCF
	--hgvsc	[hgvsc]			    input HGVSC
	--regions [regions]		    regions to slice input on
    --convert                   flag to run conversion only, not annotation
	-o|--outfolder [outfolder]	output folder (default: working directory)

"

# Parse arguments
WORKDIR=$PWD
CONVERT_ONLY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --vcf)
      if [[ $2 = -* ]]; then echo "Need argument for $1"; exit 1; fi
      VCF="$2"
      shift
      ;;
    --hgvsc)
      if [[ $2 = -* ]]; then echo "Need argument for $1"; exit 1; fi
      HGVSC="$2"
      shift
      ;;
    --regions)
      if [[ $2 = -* ]]; then echo "Need argument for $1"; exit 1; fi
      REGIONS="$2"
      shift
      ;;
    --help|-h)
      echo "$usage"
      exit 0
      ;;
    --outfolder|-o)
      if [[ $2 = -* ]]; then echo "Need argument for $1"; exit 1; fi
      WORKDIR="$2"
      shift
      ;;
    --convert)
      CONVERT_ONLY=1
      ;;
    *)
      echo "* Error: Invalid argument: $1"
      echo "$usage"
      exit 1

  esac
  shift
done

if [ ! -z $HGVSC ] && [ ! -z $VCF ]
then
    echo "Both HGVSC and VCF provided. Exiting."
    exit 1
fi

if [ -z $HGVSC ] && [ -z $VCF ]
then
    echo "Neither VCF or HGVSC provded. Exiting."
    exit 1
fi

if [ -z $FASTA ] || [ -z $ANNO ]
then
    echo "Missing one or more mandatory environment variables:"
    echo "FASTA: $FASTA"
    echo "ANNO: $ANNO"
    exit 1
fi

ANNODATA="${SOURCE_DIR}/../../data"
VCFANNO_CONFIG="${SOURCE_DIR}/vcfanno_config.toml"

echo "ANNO version:"
cat ${SOURCE_DIR}/../../version
echo ""
echo "Running annotation pipeline with: "
echo "VCF: $VCF"
echo "HGVSC: $HGVSC"
echo "REGIONS: $REGIONS"
echo "WORKDIR: $WORKDIR"
echo "CONVERT_ONLY: $CONVERT_ONLY"


# End parse arguments

set -e
cleanup()
{
    EXIT_CODE=$?
    if [ ! $EXIT_CODE -eq 0 ]
    then
        handle_step_failed
    fi
    exit $EXIT_CODE
}

# Trap EXIT code to run cleanup function
trap cleanup EXIT

mkdir -p $WORKDIR

### Reused functions

handle_step_done ()
{
    echo -e "$(date '+%Y-%m-%d %H:%M:%S.%N')\t$STEP\tDONE" | tee -a $STATUS_FILE
    touch $OUTPUT_SUCCESS
    VCF=$OUTPUT_VCF
}

handle_step_failed ()
{
    echo -e "$(date '+%Y-%m-%d %H:%M:%S.%N')\t$STEP\tFAILED" | tee -a $STATUS_FILE
    cp $OUTPUT_LOG "$WORKDIR/error.log"
    touch $OUTPUT_FAILED
    echo "--FAILED"
    cat $OUTPUT_LOG
}

handle_step_start ()
{
    STEP=$1
    WORKDIR_STEP="$WORKDIR/$STEP"
    mkdir -p $WORKDIR_STEP
    OUTPUT_LOG="$WORKDIR_STEP/output.log"
    OUTPUT_VCF="$WORKDIR_STEP/output.vcf"
    OUTPUT_CMD="$WORKDIR_STEP/cmd.sh"
    OUTPUT_SUCCESS="$WORKDIR_STEP/SUCCESS"
    OUTPUT_FAILED="$WORKDIR_STEP/FAILED"

    echo -e "$(date '+%Y-%m-%d %H:%M:%S.%N')\t$STEP\tSTARTED" | tee -a $STATUS_FILE
}

### End reused functions


### Set output folders

STATUS_FILE=$WORKDIR"/STATUS"
echo -e "$(date '+%Y-%m-%d %H:%M:%S.%N')\tSTARTED\t" | tee -a $STATUS_FILE

FINISH_FILE=$WORKDIR"/FINISHED"
if [ -f $FINISH_FILE ]
then
    echo "Removing old finish file"
    rm $FINISH_FILE
fi

FINAL_VCF=$WORKDIR"/output.vcf"
if [ -f $FINAL_VCF ]
then
    echo "Removing old final vcf"
    rm $FINAL_VCF
fi

### End set output folders

##################################
########### CONVERT ##############
##################################
if [ ! -z $HGVSC ]
then
    # Set environment variables for step
    handle_step_start "CONVERT"

    # Create and run command
    cmd="python $ANNO/src/conversion/convert.py $HGVSC $OUTPUT_VCF &> $OUTPUT_LOG"
    echo $cmd > $OUTPUT_CMD
    bash $OUTPUT_CMD

    # Handle step exit
    handle_step_done
fi

# Store original VCF
# For use in targets
cp $VCF $WORKDIR/original.vcf

##################################
########### SLICING ##############
##################################
if [ ! -z $REGIONS ]
then
    # Set environment variables for step
    handle_step_start "SLICE"

    cmd="bedtools intersect -header -wa -u -a $VCF -b $REGIONS > $OUTPUT_VCF 2> $OUTPUT_LOG"
    echo $cmd > $OUTPUT_CMD
    bash $OUTPUT_CMD

    handle_step_done
    ln -s $WORKDIR/SLICE/output.vcf $WORKDIR/sliced.vcf
fi

##################################
########### VALIDATE #############
##################################
handle_step_start "VALIDATE"

cmd="validate_vcf --input $VCF --output $OUTPUT_VCF &> $OUTPUT_LOG"
echo $cmd > $OUTPUT_CMD
bash $OUTPUT_CMD

handle_step_done

# Run annotation if not specified to run convert only
if [ $CONVERT_ONLY = 0 ]
then

    ##################################
    ######### VT DECOMPOSE ###########
    ##################################

    # Set environment variables for step
    handle_step_start "VT_DECOMPOSE"

    # Fix wrong header for older GATK
    sed -i 's/##FORMAT=<ID=AD,Number=\./##FORMAT=<ID=AD,Number=R/g' $VCF

    cmd="vt decompose -s -o $OUTPUT_VCF $VCF &> $OUTPUT_LOG"
    echo $cmd > $OUTPUT_CMD
    bash $OUTPUT_CMD

    handle_step_done

    ##################################
    ######### VT NORMALIZE ###########
    ##################################
    handle_step_start "VT_NORMALIZE"

    cmd="vt normalize -r $FASTA -o $OUTPUT_VCF $VCF &> $OUTPUT_LOG"
    echo $cmd > $OUTPUT_CMD
    bash $OUTPUT_CMD

    handle_step_done

    ##################################
    ############ VCFSORT #############
    ##################################
    handle_step_start "VCFSORT"
    cmd="cat $VCF | vcf-sort -c > $OUTPUT_VCF 2> $OUTPUT_LOG"
    echo $cmd > $OUTPUT_CMD
    bash $OUTPUT_CMD

    handle_step_done

    ##################################
    ############## VEP ###############
    ##################################
    handle_step_start "VEP"
    cmd="vep_offline \
            --fasta $FASTA \
            --force_overwrite \
            --sift=b \
            --polyphen=b \
            --hgvs \
            --numbers \
            --domains \
            --regulatory \
            --canonical \
            --protein \
            --biotype \
            --pubmed \
            --symbol \
            --allow_non_variant \
            --fork=4 \
            --vcf \
            --allele_number \
            --no_escape \
            --failed=1 \
            --no_stats \
            --merged \
            --custom ${ANNODATA}/RefSeq/GRCh37_refseq_$(jq -r '.refseq.version' $ANNO/sources.json)_VEP.gff.gz,RefSeq_gff,gff,overlap,1, \
            --custom ${ANNODATA}/RefSeq_interim/GRCh37_refseq_interim_$(jq -r '.refseq_interim.version' $ANNO/sources.json)_VEP.gff.gz,RefSeq_Interim_gff,gff,overlap,1, \
            -i $VCF \
            -o $OUTPUT_VCF &> $OUTPUT_LOG"
    echo $cmd > $OUTPUT_CMD
    bash $OUTPUT_CMD

    handle_step_done

    ##################################
    ############ VCFANNO #############
    ##################################
    handle_step_start "VCFANNO"

    cp $VCFANNO_CONFIG "$WORKDIR_STEP/vcfanno_config.toml"
    cmd="vcfanno -base-path $ANNODATA $WORKDIR_STEP/vcfanno_config.toml $VCF > $OUTPUT_VCF 2> $OUTPUT_LOG"
    echo $cmd > $OUTPUT_CMD
    bash $OUTPUT_CMD

    handle_step_done
fi

# Create link to final vcf
ln -s $VCF $FINAL_VCF
echo -e "$(date '+%Y-%m-%d %H:%M:%S.%N')\tFINALIZED\t" | tee -a $STATUS_FILE
