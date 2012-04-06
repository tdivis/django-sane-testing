from djangosanetesting.cases import NoCleanupDatabaseTestCase, NonIsolatedDatabaseTestCase, \
    NonIsolatedDestructiveDatabaseTestCase
from testapp.models import ExampleModel

# These tests are here to test non-isolated test cases, order is important here and
# they can (and will) fail if they are run in wrong order or alone.
# Purpose of non-isolated test is to avoid slow flushes and fixtures loading, if your 
# tests specifically don't need to be rock solid standalone, you can save second or even
# tens of second (on big databases) because you won't be flushing database.

class TestAAANoCleanupCase(NoCleanupDatabaseTestCase):
    fixtures = ["random_model_for_testing"]

    def test_a_model_loaded(self):
        self.assert_equals(2, len(ExampleModel.objects.all()))

    def test_b_model_loaded(self):
        self.assert_equals(2, len(ExampleModel.objects.all()))
        ExampleModel.objects.create(name="test1")

    def test_c_model_loaded(self):
        self.assert_equals(3, len(ExampleModel.objects.all()))


class TestBBBNonIsolated(NonIsolatedDatabaseTestCase):
    fixtures = ["random_model2_for_testing"]

    def test_a_model_loaded(self):
        self.assert_equals(3, len(ExampleModel.objects.all()))

    def test_b_model_loaded(self):
        self.assert_equals(3, len(ExampleModel.objects.all()))
        ExampleModel.objects.create(name="test1")

    def test_c_model_loaded(self):
        self.assert_equals(4, len(ExampleModel.objects.all()))


# TestBBBNonIsolated did rolback at end, so we can continue with 3 object in DB:
class TestCCCNonIsolated(NonIsolatedDestructiveDatabaseTestCase):
    fixtures = ["random_model2_for_testing"]

    def test_a_model_loaded(self):
        self.assert_equals(3, len(ExampleModel.objects.all()))

    def test_b_model_loaded(self):
        self.assert_equals(3, len(ExampleModel.objects.all()))
        ExampleModel.objects.create(name="test1")

    def test_c_model_loaded(self):
        self.assert_equals(4, len(ExampleModel.objects.all()))


# TestCCCNonIsolated did flush, so there should be no object in DB:
class TestDDDCleanupWasDone(NoCleanupDatabaseTestCase):
    def test_no_model_loaded(self):
        self.assert_equals(0, len(ExampleModel.objects.all()))
