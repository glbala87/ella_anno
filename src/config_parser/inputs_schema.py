"""
Specify a set of environmental variables needed. The constraints and
validations for each variable will be enforced at runtime.
"""

from typing import Literal
from pydantic import BaseSettings, constr


class ParserInputs(BaseSettings):
    """
    required environmental variables
    """
    SAMPLE_ID: constr(regex=r'.*(wgs|EKG|excap).*')
    GP_NAME: str
    GP_VERSION: str
    TYPE: Literal['single', 'trio']
    CAPTUREKIT: str

    class Config:
        case_sensitive = True
        env_prefix = ''


if __name__ == "__main__":
    p = ParserInputs()
    print(p.json(indent=4))
