import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Extra, FilePath, BaseSettings

logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

# Settings
class Settings(BaseSettings):
    """
    required environment variables
    """
    GLOBAL_CONFIG_PATH: FilePath = 'global_config.json'
    SAMPLE_ID: str
    GP_NAME: str
    GP_VERSION: str
    TYPE: str
    CAPTUREKIT: str

    class Config:
        case_sensitive = True
        fields = {
            'GLOBAL_CONFIG_PATH': {
                'env': 'ANNO_GLOBAL_CONFIG_PATH'  # external environment var name
            }
        }

    def __getitem__(self, item):
        return self.dict()[item]


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


# Parser
def parse_config(settings: Settings) -> ParsedConfig:
    global_config = GlobalConfig.parse_file(settings.GLOBAL_CONFIG_PATH)

    accumulate_config = {}

    for subconfig in global_config:
        log.info('checking %s ...', subconfig.comment)
        for environment_key, regex in subconfig.regexes.items():
            env_value = settings[environment_key]
            log.debug('checking %s "%s" against regex "%s" ...', environment_key, env_value, regex)
            if not re.match(regex, env_value):
                log.debug('not matching, skip %s', subconfig.comment)
                # only when all regexes match, is its config used
                break
            else:
                log.debug('matched')
        else:
            log.info('all regexes matched, update config with %s', subconfig.config)
            accumulate_config.update(subconfig.config)

    parsed_config = ParsedConfig.parse_obj(accumulate_config)

    return parsed_config


def main():
    settings = Settings()
    parsed_config = parse_config(settings)
    print(parsed_config.json(indent=4))


if __name__ == "__main__":
    main()
