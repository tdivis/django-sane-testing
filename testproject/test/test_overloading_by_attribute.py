from djangosanetesting.cases import NoCleanupDatabaseTestCase
from testapp.models import ExampleModel
from nose.plugins.attrib import attr

class TestOverloadingByAttribute(NoCleanupDatabaseTestCase):
    @attr(database_single_transaction=True)
    def test_aaa_no_cleanup(self):
        ExampleModel.objects.create(name="test1")
        self.assert_equals(1, len(ExampleModel.objects.all()))

    def test_bbb_model_no_longer_available(self):
        self.assert_equals(0, len(ExampleModel.objects.all()))
