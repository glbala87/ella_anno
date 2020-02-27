import os

config = {
    "verbose": bool(int(os.environ.get("VERBOSE", 1))),
    "work_folder": os.environ["WORKFOLDER"],
    "annotate_script": os.path.join(os.path.split(os.path.abspath(__file__))[0], "annotation/annotate.sh"),
    "convert": {"fail_on_conversion_error": True, "replace_ref_if_mismatch": True},
}
