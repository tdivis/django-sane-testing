from nose.tools import assert_equals #@UnresolvedImport pylint: disable=E0611
from testapp.models import ExampleModel

# database from test in test_bbb_cleaned.py left one example model:
def test_aaa__model_still_available():
    assert_equals(1, len(ExampleModel.objects.all()))
