import pytest
import json

from api import app
from api.main import api
import os


class FlaskClientProxy(object):
    def __init__(self, url_prefix="/api/v1/"):
        app.testing = True
        api.init_app(app)
        self.app = app
        self.url_prefix = url_prefix

    def get(self, url):
        with self.app.test_client() as client:
            return client.get(self.url_prefix + url, content_type="application/json")

    def post(self, url, data):
        with self.app.test_client() as client:
            return client.post(
                self.url_prefix + url,
                data=json.dumps(data),
                content_type="application/json",
            )

    def post_files(self, url, files, data=None):
        _data = {name: (file, "{}".format(name)) for name, file in files.items()}
        if data:
            _data.update(data)

        with self.app.test_client() as client:
            return client.post(
                self.url_prefix + url, data=_data, content_type="multipart/form-data"
            )

    def put(self, url, data, files=None):
        with self.app.test_client() as client:
            return client.put(
                self.url_prefix + url,
                data=json.dumps(data),
                content_type="application/json",
            )

    def patch(self, url, data, files=None):
        with self.app.test_client() as client:
            return client.patch(
                self.url_prefix + url,
                data=json.dumps(data),
                content_type="application/json",
            )

    def delete(self, url, data, files=None):
        with self.app.test_client() as client:
            return client.delete(
                self.url_prefix + url,
                data=json.dumps(data),
                content_type="application/json",
            )


@pytest.fixture
def client():
    """
    Fixture for a flask client proxy, that supports get, post etc.
    """
    c = FlaskClientProxy()
    return c


@pytest.fixture
def vcf():
    filename = os.path.join(os.path.dirname(__file__), "../testdata/brca_sample_composed.vcf")
    with open(filename, "r") as f:
        data = f.read()
    return data
