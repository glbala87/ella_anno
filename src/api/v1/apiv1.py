from . import resources


class ApiV1(object):
    def __init__(self, app, api):
        self.app = app
        self.api = api

    def _add_resource(self, resource, *paths):
        self.api.add_resource(resource, *paths, strict_slashes=False)

    def setup_api(self):
        self._add_resource(resources.annotate.AnnotateResource, "/api/v1/annotate/")

        self._add_resource(resources.convert.ConvertResource, "/api/v1/convert/")

        self._add_resource(
            resources.status.StatusResource,
            "/api/v1/status/",
            "/api/v1/status/<int:id>",
        )

        self._add_resource(resources.reset.ResetResource, "/api/v1/reset")

        self._add_resource(
            resources.process.ProcessResource, "/api/v1/process/<int:id>"
        )

        self._add_resource(resources.debug.DebugResource, "/api/v1/debug/<int:id>")

        self._add_resource(resources.cancel.CancelResource, "/api/v1/cancel/<int:id>")

        self._add_resource(resources.diagnose.DiagnoseResource, "/api/v1/diagnose")

        self._add_resource(resources.configresource.ConfigResource, "/api/v1/config")

        self._add_resource(
            resources.list_samples.ListSamplesResources, "/api/v1/samples"
        )

        self._add_resource(
            resources.annotate_sample.AnnotateSampleResource, "/api/v1/samples/annotate"
        )

        self._add_resource(resources.delete.DeleteResource, "/api/v1/delete/<int:id>")
