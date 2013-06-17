import re
import urllib2

from django.template import Context, Template, TemplateSyntaxError
from django.test import TestCase
from nose import SkipTest

from djangosanetesting.utils import twill_patched_go, twill_xpath_go, extract_django_traceback


__all__ = ("UnitTestCase", "DatabaseTestCase", "DestructiveDatabaseTestCase",
           "HttpTestCase", "SeleniumTestCase", "TemplateTagTestCase")


##########
### Scraping heavily inspired by nose testing framework, (C) by Jason Pellerin
### and respective authors.
##########

# This is descendant of the django TestCase, that means it has all features of unittest2
class _DummyTestCase(TestCase):
    def test_dummy(self):
        pass

_DUMMY = _DummyTestCase('test_dummy')
CAPS = re.compile('([A-Z])')


def pepify(name):
    """
    Transforms attribute names from camel case to underscored.
    """
    return CAPS.sub(lambda m: '_' + m.groups()[0].lower(), name)


def scrape(target):
    """
    Scrapes attributes from `django.test.TestCase` to target object.
    """
    non_magic = [attr for attr in dir(_DUMMY) if not attr.startswith('__') and not attr.endswith('__')]
    for attr in non_magic:
        # Do not scrape overriden attributes
        if hasattr(target, attr):
            continue

        value = getattr(_DUMMY, attr)
        if hasattr(value, 'im_func'):
            # If attribute is a method, unbind it and then bind it to the new object
            unbound = value.im_func
            value = unbound.__get__(target, target.__class__)
        setattr(target, attr, value)
        # Pepify only public methods
        if not attr.startswith('_'):
            setattr(target, pepify(attr), value)


class SaneTestCase(object):
    """ Common ancestor we're using our own hierarchy """
    start_live_server = False
    database_single_transaction = False
    database_flush = False
    selenium_start = False
    no_database_interaction = False
    need_db_on_load = False # useful if you need database in setup/setup_class
    make_translations = True

    required_sane_plugins = None

    SkipTest = SkipTest

    def __new__(cls, *args, **kwargs):
        """
        When constructing class, add methods from unittest(2),
        both camelCase and pep8-ify style.

        """
        obj = super(SaneTestCase, cls).__new__(cls, *args, **kwargs)
        scrape(obj)
        return obj

    def check_plugins(self):
        if getattr(self, 'required_sane_plugins', False):
            for plugin in self.required_sane_plugins:
                if not getattr(self, "%s_plugin_started" % plugin, False):
                    raise self.SkipTest("Plugin %s from django-sane-testing required, skipping" % plugin)


class UnitTestCase(SaneTestCase):
    """
    This class is a unittest, i.e. do not interact with database et al
    and thus not need any special treatment.
    """
    no_database_interaction = True
    test_type = "unit"

    def __init__(self, *args, **kwargs):
        super(UnitTestCase, self).__init__(*args, **kwargs)
        self._django_client = None

    # undocumented client: can be only used for views that are *guaranteed*
    # not to interact with models
    def get_django_client(self):
        from django.test import Client
        if not getattr(self, '_django_client', False):
            self._django_client = Client()
        return self._django_client

    def set_django_client(self, value):
        self._django_client = value

    client = property(fget=get_django_client, fset=set_django_client)


class DatabaseTestCase(SaneTestCase):
    """
    Tests using database for models in simple: rollback on teardown and we're out.

    However, we must check for fixture difference, if we're using another fixture, we must flush database anyway.
    """
    database_single_transaction = True
    database_flush = False
    required_sane_plugins = ["django"]
    django_plugin_started = False
    test_type = "database"

    def __init__(self, *args, **kwargs):
        super(DatabaseTestCase, self).__init__(*args, **kwargs)
        self._django_client = None

    def get_django_client(self):
        from django.test import Client
        if not getattr(self, '_django_client', False):
            self._django_client = Client()
        return self._django_client

    def set_django_client(self, value):
        self._django_client = value

    client = property(fget=get_django_client, fset=set_django_client)


class NoCleanupDatabaseTestCase(DatabaseTestCase):
    '''
    Initiates test database but have no cleanup utility at all (no rollback, no flush).
    Useful for example when cleanup is done by module-level attribute or pure read-only tests.
    '''
    database_single_transaction = False


class DestructiveDatabaseTestCase(DatabaseTestCase):
    """
    Test behaving so destructively that it needs database to be flushed.
    """
    database_single_transaction = False
    database_flush = True
    test_type = "destructivedatabase"


class NonIsolatedDatabaseTestCase(DatabaseTestCase):
    """
    Like DatabaseTestCase, but rollback transaction only once - after test case.
    That means tests in test case are not isolated but run faster.
    """
    database_single_transaction = False
    database_flush = False
    database_single_transaction_at_end = True


class NonIsolatedDestructiveDatabaseTestCase(DestructiveDatabaseTestCase):
    """
    Like DestructiveDatabaseTestCase, but flushing db only once - after test case.
    That means tests in test case are not isolated but run much faster.
    """
    database_single_transaction = False
    database_flush = False
    database_flush_at_end = True


class HttpTestCase(DestructiveDatabaseTestCase):
    """
    If it is not running, our plugin should start HTTP server
    so we can use it with urllib2 or some webtester.
    """
    start_live_server = True
    required_sane_plugins = ["django", "http"]
    http_plugin_started = False
    test_type = "http"

    def __init__(self, *args, **kwargs):
        super(HttpTestCase, self).__init__(*args, **kwargs)

        self._twill = None
        self._spynner = None

    def get_twill(self):
        if not self._twill:
            try:
                from twill import get_browser
            except ImportError:
                raise SkipTest("Twill must be installed if you want to use it")

            self._twill = get_browser()
            self._twill.go = twill_patched_go(browser=self._twill, original_go=self._twill.go)
            self._twill.go_xpath = twill_xpath_go(browser=self._twill, original_go=self._twill.go)

            from twill import commands
            self._twill.commands = commands

        return self._twill

    twill = property(fget=get_twill)

    def get_spynner(self):
        if not self._spynner:
            try:
                import spynner # @UnresolvedImport pylint: disable=F0401
            except ImportError:
                raise SkipTest("Spynner must be installed if you want to use it")

            self._spynner = spynner.Browser()

        return self._spynner

    spynner = property(fget=get_spynner)


    def assert_code(self, code):
        self.assert_equals(int(code), self.twill.get_code())

    def urlopen(self, *args, **kwargs): # pylint: disable=R0201
        """
        Wrap for the urlopen function from urllib2
        prints django's traceback if server responds with 500
        """
        try:
            return urllib2.urlopen(*args, **kwargs)
        except urllib2.HTTPError, err:
            if err.code == 500:
                raise extract_django_traceback(http_error=err)
            else:
                raise err

    def tearDown(self):
        if self._spynner:
            self._spynner.close()


class SeleniumTestCase(HttpTestCase):
    """
    Connect to selenium RC and provide it as instance attribute.
    Configuration in settings:
      * SELENIUM_HOST (default to localhost)
      * SELENIUM_PORT (default to 4444)
      * SELENIUM_BROWSER_COMMAND (default to *opera)
      * SELENIUM_URL_ROOT (default to URL_ROOT default to /)
    """
    selenium_start = True
    start_live_server = True
    required_sane_plugins = ["django", "selenium", "http"]
    selenium_plugin_started = False
    test_type = "selenium"


class TemplateTagTestCase(UnitTestCase):
    """
    Allow for sane and comfortable template tag unit-testing.

    Attributes:
    * `preload' defines which template tag libraries are to be loaded
      before rendering the actual template string
    * `TemplateSyntaxError' is bundled within this class, so that nothing
      from django.template must be imported in most cases of template
      tag testing
    """

    TemplateSyntaxError = TemplateSyntaxError
    preload = ()

    def render_template(self, template, **kwargs):
        """
        Render the given template string with user-defined tag modules
        pre-loaded (according to the class attribute `preload').
        """

        loads = u''
        for load in self.preload:
            loads = u''.join([loads, '{% load ', load, ' %}'])

        template = u''.join([loads, template])
        return Template(template).render(Context(kwargs))
