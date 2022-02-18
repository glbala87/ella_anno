"""
This scipts parse and validate a configuration file and generate a json file by
matching environment variable values to regexes in the configuration file.
"""
import os
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Extra, FilePath, BaseSettings

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

PARSED_CONFIG_FILE = 'task_config.json'


# Settings
class Settings(BaseSettings):
    """
    path to configuration file
    """
    CONFIG_PATH: FilePath


# Schemas of global config
class GlobalConfigItem(BaseModel):
    comment: str
    regexes: Dict[str, str]
    config: Dict[str, bool]

    class Config:
        extra = Extra.forbid


class GlobalConfig(BaseModel):
    __root__: List[GlobalConfigItem]

    def __iter__(self):
        return iter(self.__root__)

    def __getitem__(self, item):
        return self.__root__[item]

    def __len__(self) -> int:
        return len(self.__root__)


# Schemas of parsed config
class ParsedConfig(BaseModel):
    __root__: Dict[str, bool]

    def __getitem__(self, item):
        return self.__root__[item]


# Parser
def parse_config(settings: Settings, environment: Dict[str, str]) -> ParsedConfig:
    # load and validate global config
    global_config = GlobalConfig.parse_file(settings.CONFIG_PATH)

    accumulate_config = {}

    for subconfig in global_config:
        log.info(' checking %s ...', subconfig.comment)
        for environment_key, regex in subconfig.regexes.items():
            if environment_key not in environment:
                raise RuntimeError(f'environment variable "{environment_key}" not set')
            env_value = environment[environment_key]
            log.debug('checking %s "%s" against regex "%s" ...', environment_key, env_value, regex)
            if not re.match(regex, env_value):
                log.debug('not matching, skip %s', subconfig.comment)
                # only when all regexes match, is its config used
                break
            else:
                log.debug('matched')
        else:
            log.info(' all regexes matched, update config with %s', subconfig.config)
            accumulate_config.update(subconfig.config)

    # validate parsed config
    parsed_config = ParsedConfig.parse_obj(accumulate_config)

    return parsed_config


def main():
    settings = Settings()
    environment = os.environ
    parsed_config = parse_config(settings, environment)
    config_json = parsed_config.json(indent=4)
    log.info('\nenvironment variables:\n%s\noutput config:\n%s',
             settings.json(indent=4),
             config_json)

    outfile = Path(PARSED_CONFIG_FILE)
    outfile.write_text(config_json)


if __name__ == "__main__":
    main()
