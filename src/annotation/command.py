import os
import jinja2


SCRIPT_DIR = os.path.abspath(os.path.dirname(__file__))


COMMAND_TEMPLATE = """
#!/bin/bash

set -euf -o pipefail

if [[ -f "${TARGETS}/targets/preprocess/{{ target }}" ]]; then
    ####
    # Preprocess for target: {{ target }}
    ####
    echo -e "$(date '+%Y-%m-%d %H:%M:%S.%N')\t{{ target|upper }} (PREPROCESS) \tSTARTED" | tee -a {{ status_file }}
    # TARGET VARIABLES
    source {{ task_dir }}/target.source

    mkdir -p {{ task_dir }}/{{ target }}
    pushd {{ task_dir }}/{{ target }}
    set +o pipefail

    # Run preprocess for target
    bash "${TARGETS}/targets/preprocess/{{ target }}" |& tee output_preprocess.log

    EXIT_CODE=${PIPESTATUS[0]}
    if [ $EXIT_CODE == 0 ]; then
        echo -e "$(date '+%Y-%m-%d %H:%M:%S.%N')\t{{ target|upper }} (PREPROCESS) \tDONE" | tee -a {{ status_file }}
    else
        echo -e "$(date '+%Y-%m-%d %H:%M:%S.%N')\t{{ target|upper }} (PREPROCESS) \tFAILED" | tee -a {{ status_file }}
        exit $EXIT_CODE
    fi
    set -o pipefail
    popd
fi

annotate \\
{%- if input_type == 'vcf' %}
    --vcf {{ input_file }} \\
{%- elif input_type == 'hgvsc' %}
    --hgvsc {{ input_file }} \\
{%- endif %}
{%- if input_regions %}
    --regions {{ input_regions }} \\
{%- endif %}
{%- if convert_only %}
    --convert \\
{%- endif %}
    -o {{ task_dir }}

{% if target %}
# Run targets
# TARGET VARIABLES
source {{ task_dir }}/target.source

####
# Target: {{ target }}
####

TASK_TARGET_OUT="{{ task_dir }}/{{ target }}/OUT"
mkdir -p "$TASK_TARGET_OUT"
cd {{ task_dir }}/{{ target }}
echo -e "$(date '+%Y-%m-%d %H:%M:%S.%N')\t{{ target|upper }}\tSTARTED" | tee -a {{ status_file }}

TARGET_OUT=${TASK_TARGET_OUT} bash "$TARGETS/targets/{{ target }}" |& tee output.log
EXIT_CODE=${PIPESTATUS[0]}
if [ $EXIT_CODE == 0 ]
then
    echo -e "$(date '+%Y-%m-%d %H:%M:%S.%N')\t{{ target|upper }}\tDONE" | tee -a {{ status_file }}
    chmod -R a+rw .
    DELIVERY_TARGET_OUT="${TARGETS_OUT__{{ target|upper }}:-$TARGETS_OUT/{{ target }}}"
    mkdir -p "${DELIVERY_TARGET_OUT}"
    echo "Copying all files"
    set +f
    # Copy data, exclude READY file(s)
    rsync -av --no-perms --exclude READY "${TASK_TARGET_OUT}"/* "${DELIVERY_TARGET_OUT}"
    # Then copy possible READY files
    rsync -av --no-perms "${TASK_TARGET_OUT}"/* --ignore-existing "${DELIVERY_TARGET_OUT}"
    set -f
else
    echo -e "$(date '+%Y-%m-%d %H:%M:%S.%N')\t{{ target|upper }}\tFAILED" | tee -a {{ status_file }}
    exit $EXIT_CODE
fi

{% endif %}

cd {{ task_dir }}
"""


class Command(object):
    def __init__(self, work_dir):
        self.work_dir = work_dir
        self.cmd = os.path.join(self.work_dir, "cmd.sh")

    def _create_target_source_file(self, input_file, target_env, input_regions=None):
        # Create target.source
        target_source_file = os.path.join(self.work_dir, "target.source")
        target_exports = {
            "anno_version": os.path.abspath(os.path.join(SCRIPT_DIR, "../../version")),
            "vcf": os.path.join(self.work_dir, "output.vcf"),
            "original_vcf": os.path.join(self.work_dir, "original.vcf"),
            "input": input_file,
        }

        if target_env:
            target_exports.update(target_env)
        if input_regions:
            target_exports["regions"] = input_regions
            target_exports["sliced_vcf"] = os.path.join(self.work_dir, "sliced.vcf")

        with open(target_source_file, "w") as f:
            for k, v in sorted(target_exports.iteritems()):
                f.write('export {}="{}"\n'.format(k.upper(), v))

    def _generate_cmd(
        self,
        input_file,
        input_type,
        input_regions=None,
        convert_only=False,
        target=None,
        target_env=None,
    ):

        assert input_file
        assert input_type in ["vcf", "hgvsc"]

        if input_regions:
            assert os.path.isfile(input_regions)

        if target:
            self._create_target_source_file(
                input_file, target_env, input_regions=input_regions
            )

        # Create cmd.sh from template
        template_vars = {
            "task_dir": self.work_dir,
            "input_file": input_file,
            "input_type": input_type,
            "input_regions": input_regions,
            "target": target,
            "status_file": os.path.join(self.work_dir, "STATUS"),
            "convert_only": convert_only,
        }
        tmpl = jinja2.Template(COMMAND_TEMPLATE)

        with open(self.cmd, "w") as f:
            f.write(tmpl.render(template_vars))

    @classmethod
    def create_from_vcf(
        cls,
        work_dir,
        input_vcf,
        input_regions=None,
        convert_only=False,
        target=None,
        target_env=None,
    ):
        assert os.path.isfile(input_vcf)
        c = cls(work_dir)

        c._generate_cmd(
            input_vcf,
            "vcf",
            input_regions=input_regions,
            convert_only=convert_only,
            target=target,
            target_env=target_env,
        )
        return c

    @classmethod
    def create_from_hgvsc(
        cls,
        work_dir,
        input_hgvsc,
        input_regions=None,
        convert_only=False,
        target=None,
        target_env=None,
    ):
        assert os.path.isfile(input_hgvsc)
        c = cls(work_dir)

        c._generate_cmd(
            input_hgvsc,
            "hgvsc",
            input_regions=input_regions,
            convert_only=convert_only,
            target=target,
            target_env=target_env,
        )
        return c
