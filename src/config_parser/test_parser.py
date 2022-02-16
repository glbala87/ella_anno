import os
import pytest
from pydantic import ValidationError
from .config_parser import Settings, parse_config


# test missing env
REQUIRED_ENVS = {
    'SAMPLE_ID': 'anything',
    'GP_NAME': 'anything',
    'GP_VERSION': 'anything',
    'TYPE': 'anything',
    'CAPTUREKIT': 'anything'
}


def remove_os_env_var(env_var):
    """
    remove the environment variable if exists
    """
    if env_var in os.environ:
        del os.environ[env_var]


@pytest.fixture
def all_envs():
    return REQUIRED_ENVS.copy()


@pytest.mark.parametrize('missing_env', REQUIRED_ENVS.keys())
def test_missing_env(all_envs, missing_env):

    remove_os_env_var(missing_env)

    del all_envs[missing_env]
    print(all_envs)

    with pytest.raises(ValidationError) as exeinfo:
        settings = Settings(**all_envs)


# test expected config

# all EKG samples should have cnv
def test_cnv_all_EKG_samples():
    envs = {
        'SAMPLE_ID': 'Diag-EKG220103-12345678901',
        'GP_NAME': 'any',
        'GP_VERSION': 'any',
        'TYPE': 'any',
        'CAPTUREKIT': 'any',
    }

    expected_config = {
        'cnv': True,
        'tracks': True,
    }

    parsed_config = parse_config(Settings(**envs))

    assert expected_config == parsed_config.__root__


# single wgs samples with specific genepanels should have cnv
@pytest.mark.parametrize('genepanel', ['Barnekreft', 'Netthinne', 'NETumor', 'Hyperpara'])
def test_cnv_single_wgs_specific_panels(genepanel):
    envs = {
        'SAMPLE_ID': 'Diag-wgs123-12345678901',
        'GP_NAME': genepanel,
        'GP_VERSION': 'any',
        'TYPE': 'single',
        'CAPTUREKIT': 'any'
    }

    expected_config = {
        'cnv': True,
        'tracks': True,
    }

    parsed_config = parse_config(Settings(**envs))

    assert expected_config == parsed_config.__root__


# single wgs samples with other genepanels should NOT have cnv
@pytest.mark.parametrize('genepanel', ['foo', 'bar'])
def test_cnv_single_wgs_other_panels(genepanel):
    envs = {
        'SAMPLE_ID': 'Diag-wgs123-12345678901',
        'GP_NAME': genepanel,
        'GP_VERSION': 'any',
        'TYPE': 'single',
        'CAPTUREKIT': 'any'
    }

    expected_config = {
        'cnv': False,
        'tracks': True,
    }

    parsed_config = parse_config(Settings(**envs))

    assert expected_config == parsed_config.__root__


# all trio wgs samples should NOT have cnv
def test_cnv_all_trio_wgs_samples():
    envs = {
        'SAMPLE_ID': 'Diag-wgs123-12345678901',
        'GP_NAME': 'any',
        'GP_VERSION': 'any',
        'TYPE': 'trio',
        'CAPTUREKIT': 'any'
    }

    expected_config = {
        'cnv': False,
        'tracks': True,
    }

    parsed_config = parse_config(Settings(**envs))

    assert expected_config == parsed_config.__root__


# all excap samples should NOT have cnv
def test_cnv_all_excap_samples():
    envs = {
        'SAMPLE_ID': 'Diag-excap123-12345678901',
        'GP_NAME': 'any',
        'GP_VERSION': 'any',
        'TYPE': 'any',
        'CAPTUREKIT': 'any'
    }

    expected_config = {
        'cnv': False,
        'tracks': True,
    }

    parsed_config = parse_config(Settings(**envs))

    assert expected_config == parsed_config.__root__
