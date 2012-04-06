from testapp.models import ExampleModel
from nose.plugins.attrib import attr
from nose.tools import assert_equals #@UnresolvedImport pylint: disable=E0611

database_single_transaction = True

def test_aaa_add_model():
    ExampleModel.objects.create(name="test1")
    assert_equals(1, len(ExampleModel.objects.all()))

def test_ddd_model_no_longer_available():
    assert_equals(0, len(ExampleModel.objects.all()))

@attr(database_single_transaction=False)
def test_ccc_add_model2():
    ExampleModel.objects.create(name="test1")
    assert_equals(1, len(ExampleModel.objects.all()))

def test_bbb_model_still_available():
    assert_equals(1, len(ExampleModel.objects.all()))
