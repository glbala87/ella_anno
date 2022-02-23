import os
import pytest
from pydantic import ValidationError
from .config_parser import Settings, parse_config

# global settings
settings = Settings()

# test 'tracks'
class TestConfig_tracks:
    def test_tracks_all_samples(self):
        envs = {
            'SAMPLE_ID': 'any',
            'GP_NAME': 'any',
            'GP_VERSION': 'any',
            'TYPE': 'any',
            'CAPTUREKIT': 'any',
        }

        expected_config = {
            'tracks': True
        }

        parsed_config = parse_config(settings, envs)[0]

        assert expected_config['tracks'] == parsed_config['tracks']


# test 'cnv'
@pytest.mark.parametrize('cnv_genepanels', ['Barnekreft', 'Netthinne', 'NETumor', 'Hyperpara'])
class TestConfig_single_wgs_cnv_panels:
    # single wgs samples with specific genepanels should have cnv
    def test_cnv_single_wgs_specific_panels(self, cnv_genepanels):
        envs = {
            'SAMPLE_ID': 'Diag-wgs123-12345678901',
            'GP_NAME': cnv_genepanels,
            'GP_VERSION': 'any',
            'TYPE': 'single',
            'CAPTUREKIT': 'any'
        }

        expected_config = {
            'cnv': True,
        }

        parsed_config = parse_config(settings, envs)[0]

        assert expected_config['cnv'] == parsed_config['cnv']

@pytest.mark.parametrize('no_cnv_genepanels', ['foo', 'bar', 'Netthinne2'])
class TestConfig_single_wgs_no_cnv_panels:
    # single wgs samples with panels other than those in cnv_genepanels should NOT have cnv
    def test_cnv_single_wgs_other_panels(self, no_cnv_genepanels):
        envs = {
            'SAMPLE_ID': 'Diag-wgs123-12345678901',
            'GP_NAME': no_cnv_genepanels,
            'GP_VERSION': 'any',
            'TYPE': 'single',
            'CAPTUREKIT': 'any'
        }

        expected_config = {
            'cnv': False,
        }

        parsed_config = parse_config(settings, envs)[0]

        assert expected_config['cnv'] == parsed_config['cnv']


class TestConfig_others_cnv:
    # all EKG samples should have cnv
    def test_cnv_all_EKG_samples(self,):
        envs = {
            'SAMPLE_ID': 'Diag-EKG220103-12345678901',
            'GP_NAME': 'any',
            'GP_VERSION': 'any',
            'TYPE': 'any',
            'CAPTUREKIT': 'any',
        }

        expected_config = {
            'cnv': True
        }

        parsed_config = parse_config(settings, envs)[0]

        assert expected_config['cnv'] == parsed_config['cnv']

    # all trio wgs samples should NOT have cnv
    def test_cnv_all_trio_wgs_samples(self):
        envs = {
            'SAMPLE_ID': 'Diag-wgs123-12345678901',
            'GP_NAME': 'any',
            'GP_VERSION': 'any',
            'TYPE': 'trio',
            'CAPTUREKIT': 'any'
        }

        expected_config = {
            'cnv': False,
        }

        parsed_config = parse_config(settings, envs)[0]

        assert expected_config['cnv'] == parsed_config['cnv']

    # all excap samples should NOT have cnv
    def test_cnv_all_excap_samples(self):
        envs = {
            'SAMPLE_ID': 'Diag-excap123-12345678901',
            'GP_NAME': 'any',
            'GP_VERSION': 'any',
            'TYPE': 'any',
            'CAPTUREKIT': 'any'
        }

        expected_config = {
            'cnv': False,
        }

        parsed_config = parse_config(settings, envs)[0]

        assert expected_config['cnv'] == parsed_config['cnv']
