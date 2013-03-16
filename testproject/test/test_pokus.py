from djangosanetesting.cases import DestructiveDatabaseTestCase
from testapp.models import ExampleModel


class TestDatabaseFlush(DestructiveDatabaseTestCase):
    def test_normal(self):
        ExampleModel.objects.create(pk=1)

    def _create_model(self):
        ExampleModel.objects.create(pk=1)

    def test_generatored_tests(self):
        for i in xrange(3):
            yield self._create_model
