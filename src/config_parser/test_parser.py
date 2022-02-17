import os
import pytest
from pydantic import ValidationError
from .config_parser import Settings, parse_config


# TEST MISSING ENVIRONMENT VARIABLE
REQUIRED_ENVS = Settings.schema()['required']

def remove_os_env_var(env_var):
    """
    remove the environment variable if exists
    """
    if env_var in os.environ:
        del os.environ[env_var]

@pytest.fixture
def all_envs():
    envs = {}
    for name in REQUIRED_ENVS:
        envs[name] = ''

    return envs

@pytest.mark.parametrize('missing_env', REQUIRED_ENVS)
def test_missing_env(all_envs, missing_env):

    remove_os_env_var(missing_env)

    del all_envs[missing_env]

    with pytest.raises(ValidationError) as exeinfo:
        settings = Settings(**all_envs)
