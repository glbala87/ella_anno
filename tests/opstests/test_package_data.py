import os
from conftest import iterate_testdata_files, ANNO_DATA, package_return_tar


def check_tar_contents(filenames, data_tar_filenames, data_tar):
    assert set(filenames) - set(data_tar_filenames) == set(["vcfanno_config.toml"])
    assert set(data_tar_filenames) - set(filenames) == set(["PACKAGES"])

    for f in set(filenames) & set(data_tar_filenames):
        tar_f = data_tar.extractfile(f)
        with open(os.path.join(ANNO_DATA, f), "rb") as data_f:
            assert data_f.read() == tar_f.read()


def test_package_data_all():
    "Test packaging all packages"
    data_tar = package_return_tar()
    data_tar_filenames = [name for name in data_tar.getnames() if data_tar.getmember(name).isfile()]
    filenames = [f for f in iterate_testdata_files()]

    check_tar_contents(filenames, data_tar_filenames, data_tar)
    assert data_tar.extractfile("PACKAGES").read() == "dataset1\ndataset2\n"
    data_tar.close()


def test_package_iterations():
    "Test packaging one dataset at a time"
    datasets = []
    for dataset in ["dataset1", "dataset2"]:
        datasets.append(dataset)
        data_tar = package_return_tar(PKG_NAMES=[dataset])
        data_tar_filenames = [name for name in data_tar.getnames() if data_tar.getmember(name).isfile()]
        filenames = [f for f in iterate_testdata_files() if any(ds in f.lower() for ds in datasets) or "/" not in f]

        check_tar_contents(filenames, data_tar_filenames, data_tar)
        assert data_tar.extractfile("PACKAGES").read() == "\n".join(datasets) + "\n"
        data_tar.close()


def test_package_single_pkg():
    "Test packaging single packages"
    for dataset in ["dataset1", "dataset2"]:
        data_tar = package_return_tar(PKG_NAMES=[dataset])
        data_tar_filenames = [name for name in data_tar.getnames() if data_tar.getmember(name).isfile()]
        filenames = [f for f in iterate_testdata_files() if dataset in f.lower() or "/" not in f]
        check_tar_contents(filenames, data_tar_filenames, data_tar)
        assert data_tar.extractfile("PACKAGES").read() == "{}\n".format(dataset)
        data_tar.close()
        os.remove(data_tar.fileobj.name)
