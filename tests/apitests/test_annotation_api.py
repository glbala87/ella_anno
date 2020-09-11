import json
from io import StringIO
import pytest
import os
import re
import tempfile
from config import config

_TESTDATA = os.path.join(os.path.dirname(__file__), "../testdata/")
SMALL_TEST_VCF = _TESTDATA + "brca_sample_composed.vcf"
LARGE_TEST_VCF = (
    _TESTDATA + "sample_repo/Diag-TargetS2-NA12878/Diag-TargetS2-NA12878.final.vcf"
)
TEST_SEQPILOT = _TESTDATA + "seqpilot_export.csv"
TEST_GENOMIC = _TESTDATA + "genomic.txt"
TEST_REGIONS = _TESTDATA + "brca1_brca2.csv"


def return_value(response):
    return json.loads(response.get_data())


@pytest.mark.parametrize(
    "input,endpoint,wait",
    [
        (SMALL_TEST_VCF, "annotate", False),
        (TEST_SEQPILOT, "annotate", False),
        (SMALL_TEST_VCF, "annotate", True),
        (TEST_SEQPILOT, "convert", False),
        (TEST_SEQPILOT, "convert", True),
        (TEST_GENOMIC, "annotate", False),
    ],
)
def test_annotate(client, input, endpoint, wait):
    if wait:
        endpoint += "?wait=True"
    response = client.post_files(endpoint, {"input": open(input, "rb")})
    if wait:
        assert response.status_code == 200
        response = client.get("status/")
        assert response.status_code == 200
        ret = return_value(response)
        task_id = sorted(ret.keys())[-1]
    else:
        assert response.status_code == 202
        ret = return_value(response)
        task_id = ret["task_id"]

        response = client.get("status/{}".format(task_id))
        assert response.status_code == 200
        ret = return_value(response)
        assert "active" in ret
        assert "status" in ret
        assert "error" in ret

        response = client.get("process/{}".format(task_id))
        assert response.status_code == 200

    response = client.get("status/{}".format(task_id))
    assert response.status_code == 200
    ret = return_value(response)
    assert ret["active"] is False
    assert ret["error"] is False
    last_item = sorted(ret["status"].keys())[-1]
    assert ret["status"][last_item] == "FINALIZED"


@pytest.mark.parametrize("endpoint", ["diagnose", "samples", "config"])
def test_info_endpoints(client, endpoint):
    response = client.get(endpoint)
    assert response.status_code == 200


def test_slice(client):
    def get_positions(vcf):
        for l in vcf:
            if l.startswith("#"):
                continue
            chrom, pos = l.split("\t")[:2]
            pos = int(pos)
            yield chrom, pos

    def get_regions(regions):
        for l in regions:
            if l.startswith("#"):
                continue
            chrom, start, stop = l.strip().split("\t")[:3]
            start, stop = int(start), int(stop)
            yield chrom, start, stop

    response = client.post_files(
        "annotate?wait=True",
        {"input": open(LARGE_TEST_VCF, "rb"), "regions": open(TEST_REGIONS, "rb")},
    )
    assert response.status_code == 200
    output_vcf = response.get_data().decode("utf-8")

    # Output contains only variants in slicing regions
    for chrom, pos in get_positions(StringIO(output_vcf)):
        next(
            r
            for r in get_regions(open(TEST_REGIONS, "r"))
            if r[0] == chrom and r[1] <= pos and r[2] >= pos
        )

    # Input contains variants outside slicing regions
    with pytest.raises(StopIteration):
        for chrom, pos in get_positions(open(LARGE_TEST_VCF, "r")):
            next(
                r
                for r in get_regions(open(TEST_REGIONS, "r"))
                if r[0] == chrom and r[1] <= pos and r[2] >= pos
            )


def test_annotate_sample(client):
    response = client.get("samples")
    samples = return_value(response)
    assert samples == json.load(
        open(os.path.join(os.environ["SAMPLES"], "samples.json"), "r")
    )

    sample_id = list(samples.keys())[0]

    response = client.post_files(
        "samples/annotate",
        files={"regions": open(TEST_REGIONS, "rb")},
        data={"sample_id": "'{}'".format(sample_id)},
    )
    assert response.status_code == 202
    ret = return_value(response)
    task_id = ret["task_id"]

    response = client.get("process/{}".format(task_id))
    assert response.status_code == 200


@pytest.mark.parametrize("target", ["dummy_target", "dummy_target_with_preprocess"])
def test_target(client, target):
    """dummy_target will create a env.txt of the output of the `env`-command."""
    response = client.get("samples")
    samples = return_value(response)

    os.environ["TARGETS_OUT"] = tempfile.mkdtemp()
    assert samples == json.load(
        open(os.path.join(os.environ["SAMPLES"], "samples.json"), "r")
    )

    sample_id = list(samples.keys())[0]
    sample = samples[sample_id]

    # Post sample, a dummy variable and dummy file, requesting the dummy_target target
    # All variables and files available in the sample json should be available in the
    # target, as well as the dummy variable and the dummy file
    tmp = tempfile.NamedTemporaryFile(delete=False)
    tmp.write(b"dabla")
    tmp.flush()
    tmp.close()

    response = client.post_files(
        "samples/annotate",
        files={"regions": open(TEST_REGIONS, "rb"), "dummy_file": open(tmp.name, "rb")},
        data={
            "sample_id": "'{}'".format(sample_id),
            "targets": "'{}'".format(target),
            "dummy_variable": "'foo'",
        },
    )
    assert response.status_code == 202
    ret = return_value(response)
    task_id = ret["task_id"]

    # Finish task
    response = client.get("process/{}".format(task_id))
    assert response.status_code == 200

    # Check that file(s) have been output
    target_output = os.path.join(os.environ["TARGETS_OUT"], target, "dummy_output")
    assert os.path.isdir(target_output)

    target_env = os.path.join(target_output, "env.txt")
    assert os.path.isfile(target_env)

    # Check that files and variables given in the samples.json are available in the target
    with open(target_env, "r") as f:
        ts = [l.strip() for l in f.readlines()]
        for k, v in list(sample.items()) + [("dummy_variable", "foo")]:
            if k == "vcf":
                k = "original_vcf"
            vt = next(
                m
                for m in [re.match("{}=(.*)".format(k.upper()), l) for l in ts]
                if m is not None
            ).group(1)

            path_candidate = os.path.join(os.environ["SAMPLES"], v)
            if os.path.isfile(path_candidate):
                assert os.path.isfile(vt)
                with open(path_candidate, "r") as fs, open(vt, "r") as ft:
                    assert fs.read() == ft.read()
            else:
                assert v == vt

    # Check that optional files are available in the work folder
    vt = next(
        m for m in [re.match("DUMMY_FILE=(.*)", l) for l in ts] if m is not None
    ).group(1)
    dummy_file_target = os.path.join(config["work_folder"], task_id, "dummy_file")
    assert os.path.samefile(vt, dummy_file_target)
    with open(tmp.name, "r") as f1, open(dummy_file_target) as f2:
        # Preprocess modified the dummy file
        if target == "dummy_target_with_preprocess":
            assert f1.read() + "\nPreprocess" == f2.read()
        else:
            assert f1.read() == f2.read()

    if target == "dummy_target_with_preprocess":
        assert os.path.isfile(
            os.path.join(
                config["work_folder"], task_id, target, "output_preprocess.log"
            )
        )

    os.unlink(tmp.name)


def test_reset(client):
    # Make sure we have some data to remove
    test_annotate(client, SMALL_TEST_VCF, "annotate", True)
    from api.v1.resources.diagnose import get_size

    assert get_size(config["work_folder"]) > 0
    response = client.get("reset")
    assert response.status_code == 204
    assert get_size(config["work_folder"]) == 0
