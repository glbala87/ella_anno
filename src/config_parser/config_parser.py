"""
This script receives a configuration json file and, optionally, an inputs
parser Python script which defines a "ParserInputs" class inheriting Pydantic
BaseSettings. 

This script outputs a task specific configuration json file by matching
environment variable values to regexes defined in the configuration file.

If no input parser script is given, environmental variable values will be used
as they are.
"""

import os
import sys
import logging
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Extra, FilePath, BaseSettings

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

PARSED_CONFIG_FILE = 'task_config.json'


# config parser settings
class Settings(BaseSettings):
    """
    :CONFIG_PATH: Required. Path to config file.
    :INPUT_SCHEMA: Optional. Path to a python script defining a class named
                    'ParserInputs' inheriting pydantic BaseSettings.
    """
    CONFIG_PATH: FilePath
    INPUT_SCHEMA: Optional[FilePath] = None

    class Config:
        case_sensitive = True
        env_prefix = 'ANNO_'  # prefix ANNO_ to avoid conflicts


# Schemas of global config
class GlobalConfigItem(BaseModel):
    comment: str
    regexes: Dict[str, str]
    config: Dict[str, Any]

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
    __root__: Dict[str, Any]

    def __getitem__(self, item):
        return self.__root__[item]


# Parser
def parse_config(settings: Settings, environment: Dict[str, str]) -> Tuple[ParsedConfig, Dict[str, Any]]:
    # load and validate global config
    global_config = GlobalConfig.parse_file(settings.CONFIG_PATH)

    used_inputs = {}
    accumulate_config = {}

    for subconfig in global_config:
        log.info(' CHECKING [ %s ] ...', subconfig.comment)
        for environment_key, regex in subconfig.regexes.items():
            if environment_key not in environment:
                raise RuntimeError(f'environment variable "{environment_key}" not set')
            env_value = environment[environment_key]
            used_inputs[environment_key] = env_value
            log.debug('checking %s="%s" against regex "%s"', environment_key, env_value, regex)
            if not re.match(regex, env_value):
                log.debug('not matched')
                log.info(' NOT ALL REGEXES MATCHED, SKIP [ %s ]', subconfig.comment)
                # only when all regexes match, is its config used
                break
            else:
                log.debug('matched')
        else:
            log.info(' ALL REGEXES MATCHED, UPDATE TASK CONFIG WITH:\n%s',
                     json.dumps(subconfig.config, indent=4))
            accumulate_config.update(subconfig.config)

    # validate parsed config
    parsed_config = ParsedConfig.parse_obj(accumulate_config)

    return parsed_config, used_inputs


def main(settings, environment):
    (parsed_config, used_inputs) = parse_config(settings, environment)
    config_json = parsed_config.json(indent=4)
    log.info('SUMMARY\nsettings:\n%s\nvariables used:\n%s\ntask config:\n%s',
             settings.json(indent=4),
             json.dumps(used_inputs, indent=4),
             config_json)

    outfile = Path(PARSED_CONFIG_FILE)
    outfile.write_text(config_json)
    log.info('task config file generated at %s', outfile.absolute())


if __name__ == "__main__":
    settings = Settings()

    if settings.INPUT_SCHEMA:
        # collect and validate required environmental variables according to given schema
        import importlib.util
        schema = settings.INPUT_SCHEMA
        module_name = schema.stem + '_for_anno_parser'
        spec = importlib.util.spec_from_file_location(module_name, settings.INPUT_SCHEMA)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        ParserInputs = getattr(mod, 'ParserInputs')

        environment = ParserInputs().dict()
    else:
        # pass all environmental variables to parser; no validation
        environment = os.environ

    main(settings, environment)
