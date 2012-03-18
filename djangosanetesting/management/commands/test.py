"""
Add extra options from the test runner to the ``test`` command, so that you can
browse all the nose options from the command line.
"""
# Taken from django_nose project

from django.conf import settings
from django.test.utils import get_runner


if 'south' in settings.INSTALLED_APPS:
    from south.management.commands.test import Command as OriginalCommand # @UnresolvedImport @UnusedImport pylint: disable=F0401
else:
    from django.core.management.commands.test import Command as OriginalCommand # @Reimport

TestRunner = get_runner(settings)

if hasattr(TestRunner, 'options'):
    extra_options = TestRunner.options
else:
    extra_options = []


class Command(OriginalCommand):
    option_list = OriginalCommand.option_list + tuple(extra_options)
