from nose.tools import assert_equals #@UnresolvedImport pylint: disable=E0611
from testapp.models import ExampleModel

# database from test in test_aaa_at_end.py got cleaned:
def test_aaa_model_no_longer_available():
    assert_equals(0, len(ExampleModel.objects.all()))

# add model for test_ccc_no_cleanup:
def test_bbb_add_model():
    ExampleModel.objects.create(name="test1")
    assert_equals(1, len(ExampleModel.objects.all()))
