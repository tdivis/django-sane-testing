from nose.tools import assert_equals #@UnresolvedImport pylint: disable=E0611
from djangosanetesting.cases import NoCleanupDatabaseTestCase
from testapp.models import ExampleModel

database_single_transaction_at_end = True

class TestAAANoCleanupCase(NoCleanupDatabaseTestCase):
    fixtures = ["random_model_for_testing"]

    def test_a_model_loaded(self):
        self.assert_equals(2, len(ExampleModel.objects.all()))

    def test_b_model_loaded(self):
        self.assert_equals(2, len(ExampleModel.objects.all()))
        ExampleModel.objects.create(name="test1")

    def test_c_model_loaded(self):
        self.assert_equals(3, len(ExampleModel.objects.all()))

def test_aaa_add_model():
    ExampleModel.objects.create(name="test2")
    assert_equals(4, len(ExampleModel.objects.all()))

def test_bbb__model_still_available():
    assert_equals(4, len(ExampleModel.objects.all()))

