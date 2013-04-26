"""
Various plugins for nose, that let us do our magic.
"""
import socket
import threading
import types
import os
from BaseHTTPServer import HTTPServer
from SocketServer import ThreadingMixIn
from time import sleep
from inspect import ismodule, isclass
import unittest

from django.core.management import call_command
from django.core.servers.basehttp import  WSGIRequestHandler, WSGIServerException
from django.core.urlresolvers import clear_url_caches
from django.test import TestCase as DjangoTestCase

import nose
from nose import SkipTest
from nose.plugins import Plugin

import djangosanetesting
from djangosanetesting import MULTIDB_SUPPORT, DEFAULT_DB_ALIAS
from djangosanetesting.cache import flush_django_cache
from djangosanetesting.contextstack import ContextStack
from djangosanetesting.utils import (
    get_databases, get_live_server_path,
    get_server_handler,
    DEFAULT_LIVE_SERVER_ADDRESS, DEFAULT_LIVE_SERVER_PORT,
)


TEST_CASE_CLASSES = (djangosanetesting.cases.SaneTestCase, unittest.TestCase)

__all__ = ("CherryPyLiveServerPlugin", "DjangoLiveServerPlugin", "DjangoPlugin", "SeleniumPlugin",
           "SaneTestSelectionPlugin", "ResultPlugin")


def flush_cache(test=None):
    from django.contrib.contenttypes.models import ContentType
    ContentType.objects.clear_cache()

    from django.conf import settings

    if (test and getattr_test(test, "flush_django_cache", False)) \
        or (not hasattr_test(test, "flush_django_cache") and getattr(settings, "DST_FLUSH_DJANGO_CACHE", False)):
        flush_django_cache()

def is_test_case_class(nose_test):
    if isclass(nose_test) and issubclass(nose_test, TEST_CASE_CLASSES):
        return True
    else:
        return False

def get_test_case_class(nose_test):
    if ismodule(nose_test) or is_test_case_class(nose_test):
        return nose_test
    if isinstance(nose_test.test, nose.case.MethodTestCase):
        return nose_test.test.test.im_class
    else:
        return nose_test.test.__class__

def get_test_case_method(nose_test):
    if not hasattr(nose_test, 'test'): # not test method/functoin, probably test module or test class (from startContext)
        return None
    if isinstance(nose_test.test, (nose.case.MethodTestCase, nose.case.FunctionTestCase)):
        return nose_test.test.test
    else:
        return getattr(nose_test.test, nose_test.test._testMethodName)

def get_test_case_instance(nose_test):
    if ismodule(nose_test) or is_test_case_class(nose_test):
        return nose_test
    if getattr(nose_test, 'test', False) and not isinstance(nose_test.test, (nose.case.FunctionTestCase)):
        return get_test_case_method(nose_test).im_self

def hasattr_test(nose_test, attr_name):
    ''' hasattr from test method or test_case.
    '''
    if nose_test is None:
        return False
    elif ismodule(nose_test) or is_test_case_class(nose_test):
        return hasattr(nose_test, attr_name)
    elif hasattr(get_test_case_method(nose_test), attr_name) or hasattr(get_test_case_instance(nose_test), attr_name):
        return True
    else:
        return False

def getattr_test(nose_test, attr_name, default=False):
    ''' Get attribute from test method, if not found then form it's test_case instance
        (meaning that test method have higher priority). If not found even
        in test_case then return default.
    '''
    test_attr = getattr(get_test_case_method(nose_test), attr_name, None)
    if test_attr is not None:
        return test_attr
    else:
        return getattr(get_test_case_instance(nose_test), attr_name, default)

def getattr_test_meth(nose_test, attr, default=None):
    """ Return attribute of test method/function """
    test_meth = get_test_case_method(nose_test)
    if test_meth is None:
        raise RuntimeError('%s is not test method/function' % nose_test)
    return getattr(test_meth, attr, default)

def enable_test(test_case, plugin_attribute):
    if not getattr(test_case, plugin_attribute, False):
        setattr(test_case, plugin_attribute, True)

def flush_database(test_case, database=DEFAULT_DB_ALIAS): # pylint: disable=W0613
    call_command('flush', verbosity=0, interactive=False, database=database)


#####
### Okey, this is hack because of #14, or Django's #3357
### We could runtimely patch basehttp.WSGIServer to inherit from our HTTPServer,
### but we'd like to have our own modifications anyway, so part of it is cut & paste
### from basehttp.WSGIServer.
### Credits & Kudos to Django authors and Rob Hudson et al from #3357
#####

class StoppableWSGIServer(ThreadingMixIn, HTTPServer):
    """WSGIServer with short timeout, so that server thread can stop this server."""
    application = None

    def __init__(self, server_address, RequestHandlerClass=None):
        HTTPServer.__init__(self, server_address, RequestHandlerClass)
        self.base_environ = None

    def server_bind(self):
        """ Bind server to socket. Overrided to store server name & set timeout"""
        try:
            HTTPServer.server_bind(self)
        except Exception, e:
            raise WSGIServerException, e
        self.setup_environ()
        self.socket.settimeout(1)

    def get_request(self):
        """Checks for timeout when getting request."""
        try:
            sock, address = self.socket.accept()
#            sock.settimeout(None)
            return (sock, address)
        except socket.timeout:
            raise

    #####
    ### Code from basehttp.WSGIServer follows
    #####
    def setup_environ(self):
        # Set up base environment
        env = self.base_environ = {}
        env['SERVER_NAME'] = self.server_name
        env['GATEWAY_INTERFACE'] = 'CGI/1.1'
        env['SERVER_PORT'] = str(self.server_port)
        env['REMOTE_HOST'] = ''
        env['CONTENT_LENGTH'] = ''
        env['SCRIPT_NAME'] = ''

    def get_app(self):
        return self.application

    def set_app(self, application):
        self.application = application


class TestServerThread(threading.Thread):
    """Thread for running a http server while tests are running."""

    def __init__(self, address, port):
        self.address = address
        self.port = port
        self._stopevent = threading.Event()
        self.started = threading.Event()
        self.error = None
        super(TestServerThread, self).__init__()

    def run(self):
        """Sets up test server and loops over handling http requests."""
        try:
            handler = get_server_handler()
            server_address = (self.address, self.port)
            httpd = StoppableWSGIServer(server_address, WSGIRequestHandler)
            #httpd = basehttp.WSGIServer(server_address, basehttp.WSGIRequestHandler)
            httpd.set_app(handler)
            self.started.set()
        except WSGIServerException, e:
            self.error = e
            self.started.set()
            return

        # Loop until we get a stop event.
        while not self._stopevent.isSet():
            httpd.handle_request()

    def join(self, timeout=None):
        """Stop the thread and wait for it to finish."""
        self._stopevent.set()
        threading.Thread.join(self, timeout)


class AbstractLiveServerPlugin(Plugin):
    def __init__(self):
        super(AbstractLiveServerPlugin, self).__init__()
        self.server_started = False
        self.server_thread = None

    def options(self, parser, env=os.environ): # pylint: disable=W0102
        Plugin.options(self, parser, env)

    def configure(self, options, config):
        Plugin.configure(self, options, config)

    def start_server(self, address=None, port=None):
        raise NotImplementedError()

    def stop_server(self):
        raise NotImplementedError()

    def check_database_multithread_compilant(self):
        # When using memory database, complain as we'd use indepenent databases
        connections = get_databases()
        for alias in connections:
            database = connections[alias]
            if database.settings_dict['NAME'] == ':memory:' and database.settings_dict['ENGINE'] in ('django.db.backends.sqlite3', 'sqlite3'):
                raise SkipTest("You're running database in memory, but trying to use live server in another thread. Skipping.")
        return True

    def beforeTest(self, test):
        # enabling test must be in beforeTest so test can be checked for is_skipped() where is also required_sane_plugin
        # check, so all plugins must be already enabled in startTest
        from django.conf import settings
        test_case = get_test_case_class(test)

        if not self.server_started and getattr_test(test, "start_live_server", False):
            self.check_database_multithread_compilant()
            self.start_server(
                address=getattr(settings, "LIVE_SERVER_ADDRESS", DEFAULT_LIVE_SERVER_ADDRESS),
                port=int(getattr(settings, "LIVE_SERVER_PORT", DEFAULT_LIVE_SERVER_PORT))
            )
            self.server_started = True

        enable_test(test_case, 'http_plugin_started')

    def startTest(self, test):
        test_case_instance = get_test_case_instance(test)
        # clear test client for test isolation
        if test_case_instance:
            test_case_instance.client = None

    def stopTest(self, test):
        test_case_instance = get_test_case_instance(test)
        if getattr_test(test, "_twill", None):
            from twill.commands import reset_browser
            reset_browser()
            test_case_instance._twill = None

    def finalize(self, result): # pylint: disable=W0613
        self.stop_server()


class DjangoLiveServerPlugin(AbstractLiveServerPlugin):
    """
    Patch Django on fly and start live HTTP server, if TestCase is inherited
    from HttpTestCase or start_live_server attribute is set to True.

    Taken from Michael Rogers implementation from http://trac.getwindmill.com/browser/trunk/windmill/authoring/djangotest.py
    """
    name = 'djangoliveserver'
    activation_parameter = '--with-djangoliveserver'

    def start_server(self, address='0.0.0.0', port=8000):
        self.server_thread = TestServerThread(address, port)
        self.server_thread.start()
        self.server_thread.started.wait()
        if self.server_thread.error:
            raise self.server_thread.error # pylint: disable=E0702

    def stop_server(self):
        if self.server_thread:
            self.server_thread.join()
        self.server_started = False

#####
### It was a nice try with Django server being threaded.
### It still sucks for some cases (did I mentioned urllib2?),
### so provide cherrypy as working alternative.
### Do imports in method to avoid CP as dependency
### Code originally written by Mikeal Rogers under Apache License.
#####

class CherryPyLiveServerPlugin(AbstractLiveServerPlugin):
    name = 'cherrypyliveserver'
    activation_parameter = '--with-cherrypyliveserver'

    def __init__(self):
        super(CherryPyLiveServerPlugin, self).__init__()
        self.httpd = None
        self.httpd_thread = None

    def start_server(self, address='0.0.0.0', port=8000):
        handler = get_server_handler()

        def application(environ, start_response):
            environ['PATH_INFO'] = environ['SCRIPT_NAME'] + environ['PATH_INFO']
            return handler(environ, start_response)

        from cherrypy.wsgiserver import CherryPyWSGIServer # @UnresolvedImport pylint: disable=F0401
        from threading import Thread
        self.httpd = CherryPyWSGIServer((address, port), application, server_name='django-test-http')
        self.httpd_thread = Thread(target=self.httpd.start)
        self.httpd_thread.start()
        #FIXME: This could be avoided by passing self to thread class starting django
        # and waiting for Event lock
        sleep(.5)

    def stop_server(self):
        if self.server_started:
            self.httpd.stop()
            self.server_started = False


class DjangoPlugin(Plugin):
    """
    Setup and teardown django test environment
    """
    activation_parameter = '--with-django'
    name = 'django'
    env_opt = 'DST_PERSIST_TEST_DATABASE'

    def __init__(self):
        super(DjangoPlugin, self).__init__()
        self.persist_test_database = None
        self.test_database_created = False
        self.old_config = None
        self.stack = ContextStack()
        self.db_rollback_done = True
        self.db_flush_done = True

    def startContext(self, context):
        #print '>>>>', context
        if getattr(context, 'need_db_on_load', None):
            if not self.test_database_created:
                self._create_test_databases()
        if isinstance(context, (types.FunctionType, types.MethodType)):
            # tests generated by generators method/functions must not be on stack, because they know nothing about
            # attributes like db_flush of test case class or module in which they exists
            return
        self.stack.push_context(context)

    def stopContext(self, context):
        #print '<<<<', context
        if isinstance(context, (types.FunctionType, types.MethodType)):
            # tests generated by generators method/functions must not be on stack, because they know nothing about
            # attributes like db_flush of test case class or module in which they exists
            return
        node = self.stack.pop()

        if self.test_database_created:
            if not self.db_rollback_done and (
                    node.database_single_transaction_at_end or
                    (self.stack and self.stack.top().database_single_transaction)
                ):
                self._do_rollback(context)

            if not self.db_flush_done and (
                    node.database_flush_at_end or
                    (self.stack and self.stack.top().database_flush)
                ):
                self._do_flush(context)

    def options(self, parser, env=os.environ): # pylint: disable=W0102
        Plugin.options(self, parser, env)

        parser.add_option(
            "", "--persist-test-database", action="store_true",
            default=env.get(self.env_opt), dest="persist_test_database",
            help="Do not flush database unless neccessary [%s]" % self.env_opt)

    def configure(self, options, config):
        Plugin.configure(self, options, config)
        self.persist_test_database = options.persist_test_database

    def setup_databases(self, verbosity, autoclobber, **kwargs):
        # Taken from Django 1.2 code, (C) respective Django authors. Modified for backward compatibility by me
        connections = get_databases()
        old_names = []
        mirrors = []

        from django.conf import settings
        if 'south' in settings.INSTALLED_APPS:
            from south.management.commands import patch_for_test_db_setup # @UnresolvedImport pylint: disable=F0401

            settings.SOUTH_TESTS_MIGRATE = getattr(settings, 'DST_RUN_SOUTH_MIGRATIONS', True)
            patch_for_test_db_setup()

        for alias in connections:
            connection = connections[alias]
            # If the database is a test mirror, redirect it's connection
            # instead of creating a test database.
            if 'TEST_MIRROR' in connection.settings_dict and connection.settings_dict['TEST_MIRROR']:
                mirrors.append((alias, connection))
                mirror_alias = connection.settings_dict['TEST_MIRROR']
                connections._connections[alias] = connections[mirror_alias]
            else:
                if 'NAME' in connection.settings_dict:
                    old_names.append((connection, connection.settings_dict['NAME']))
                else:
                    old_names.append((connection, connection.settings_dict['DATABASE_NAME']))

                orig_settings_dict = connection.settings_dict.copy()
                try:
                    connection.creation.create_test_db(verbosity=verbosity, autoclobber=autoclobber)
                except Exception:
                    # Prevent creation of multiple databases with test_ prefix (e.g. test_db, test_test_db, ...)
                    connection.close()
                    connection.settings_dict = orig_settings_dict
                    raise

        return old_names, mirrors

    def teardown_databases(self, old_config, verbosity, **kwargs):
        # Taken from Django 1.2 code, (C) respective Django authors
        connections = get_databases()
        old_names, mirrors = old_config
        # Point all the mirrors back to the originals
        for alias, connection in mirrors:
            connections._connections[alias] = connection
        # Destroy all the non-mirror databases
        for connection, old_name in old_names:
            connection.creation.destroy_test_db(old_name, verbosity)

        self.test_database_created = False

    def begin(self):
        from django.test.utils import setup_test_environment
        setup_test_environment()
        self.test_database_created = False

    def prepareTestRunner(self, runner): # pylint: disable=W0613
        """
        Before running tests, flush the cache
        """
        flush_cache()

    def finalize(self, result): # pylint: disable=W0613
        """
        At the end, tear down our testbed
        """
        from django.test.utils import teardown_test_environment
        teardown_test_environment()

        if not self.persist_test_database and getattr(self, 'test_database_created', None):
            self.teardown_databases(self.old_config, verbosity=False)

    def beforeTest(self, test):
        # enabling test must be in beforeTest so test can be checked for is_skipped() where is also required_sane_plugin
        # check, so all plugins must be already enabled in startTest
        test_case = get_test_case_class(test)
        if issubclass(test_case, DjangoTestCase):
            return
        if getattr_test(test_case, 'multi_db', False) and not MULTIDB_SUPPORT:
            raise SkipTest("I need multi db support to run, skipping..")

        enable_test(test_case, 'django_plugin_started')

    def startTest(self, test):
        """
        When preparing test, check whether to make our database fresh
        """
        test_case = get_test_case_class(test)
        if issubclass(test_case, DjangoTestCase):
            return



        #####
        ### FIXME: It would be nice to separate handlings as plugins et al...but what 
        ### about the context?
        #####

        from django.core import mail
        from django.conf import settings
        from django.db import transaction

        test_case = get_test_case_class(test)
        test_case_instance = get_test_case_instance(test)
        if isinstance(test_case_instance, djangosanetesting.cases.SaneTestCase):
            test_case_instance.check_plugins()

        mail.outbox = []

        # clear URLs if needed
        if hasattr(test_case, 'urls'):
            test_case._old_root_urlconf = settings.ROOT_URLCONF
            settings.ROOT_URLCONF = test_case.urls
            clear_url_caches()

        #####
        ### Database handling follows
        #####
        if  getattr_test_meth(test, 'no_database_interaction', None) or self.stack.top().no_database_interaction:
            # for true unittests, we don't need database handling,
            # as unittests by definition do not interacts with database
            return

        if not self.test_database_created:
            self._create_test_databases()

        # make self.transaction available
        test_case.transaction = transaction

        # detect if we are in single transaction mode:
        if (getattr_test_meth(test, "database_single_transaction", False)
            or (not getattr_test_meth(test, "database_flush", False) and self.stack.is_transaction())):
            is_transaction = True
        else:
            is_transaction = False
        # start transaction if needed:
        if self.db_rollback_done and is_transaction:
            transaction.enter_transaction_management()
            transaction.managed(True)
            self.db_rollback_done = False
        # we are in database test, so we need to reset this flag:
        self.db_flush_done = False

        # don't use commits if we are in single_transaction mode
        self._prepare_tests_fixtures(test, commit=not is_transaction)

    def stopTest(self, test):
        """
        After test is run, clear urlconf, caches and database
        """
        test_case = get_test_case_class(test)
        test_case_instance = get_test_case_instance(test)

        # Call unittest's doCleanups
        if hasattr(test_case_instance, 'doCleanups'):
            test_case_instance.doCleanups()

        if issubclass(test_case, DjangoTestCase):
            return

        from django.conf import settings

        if hasattr(test_case, '_old_root_urlconf'):
            settings.ROOT_URLCONF = test_case._old_root_urlconf
            clear_url_caches()
        flush_cache(test)

        if getattr_test(test, 'no_database_interaction', False):
            # for true unittests, we can leave database handling for later,
            # as unittests by definition do not interacts with database
            return

        if not self.db_rollback_done and (
                getattr_test_meth(test, 'database_single_transaction') or
                (getattr_test_meth(test, 'database_single_transaction') is None and self.stack.top().database_single_transaction)
            ):
            self._do_rollback(test)
        if not self.db_flush_done and (
                getattr_test_meth(test, "database_flush") or
                (getattr_test_meth(test, 'database_flush') is None and self.stack.top().database_flush)
            ):
            self._do_flush(test)

    def _get_databases(self):
        try:
            from django.db import connections
        except ImportError:
            from django.db import connection
            connections = {DEFAULT_DB_ALIAS : connection}
        return connections

    def _get_tests_databases(self, multi_db):
        ''' Get databases for flush: according to test's multi_db attribute
            only defuault db or all databases will be flushed.
        '''
        connections = self._get_databases()
        if multi_db:
            if not MULTIDB_SUPPORT:
                raise RuntimeError('This test should be skipped but for a reason it is not')
            else:
                databases = connections
        else:
            if MULTIDB_SUPPORT:
                databases = [DEFAULT_DB_ALIAS]
            else:
                databases = connections
        return databases

    def _prepare_tests_fixtures(self, test, commit):
        fixtures = self.stack.get_unloaded_fixtures().union(getattr_test_meth(test, 'fixtures', []))
        if fixtures:
            for db in self._get_tests_databases(getattr_test(test, 'multi_db')):
                call_command('loaddata', *fixtures,
                             **{'verbosity': 0, 'commit' : commit, 'database' : db})
        self.stack.set_attr_whole_stack('fixtures_loaded', True)

    def _create_test_databases(self):
        from django.conf import settings
        connections = self._get_databases()

        database_created = False
        if not self.persist_test_database:
            self.old_config = self.setup_databases(verbosity=False, autoclobber=True)
            database_created = self.test_database_created = True
        else:
            # switch to test database, find out whether it exists, if so, use it, otherwise create a new:
            for connection in connections.all():
                connection.close()
                old_db_name = connection.settings_dict["NAME"]
                connection.settings_dict["NAME"] = connection.creation._get_test_db_name()
                try:
                    connection.cursor()
                except Exception: # pylint: disable=W0703
                    # test database doesn't exist, create it as normally:
                    connection.settings_dict["NAME"] = old_db_name # return original db name
                    connection.creation.create_test_db()
                    database_created = True

                connection.features.confirm()
                self.test_database_created = True

        if database_created:
            for db in connections:
                if 'south' in settings.INSTALLED_APPS and getattr(settings, 'DST_RUN_SOUTH_MIGRATIONS', True):
                    call_command('migrate', database=db)

                if getattr(settings, "FLUSH_TEST_DATABASE_AFTER_INITIAL_SYNCDB", False):
                    getattr(settings, "TEST_DATABASE_FLUSH_COMMAND", flush_database)(self, database=db)

    def _do_flush(self, test):
        from django.conf import settings
        for db in self._get_tests_databases(getattr_test(test, 'multi_db')):
            getattr(settings, "TEST_DATABASE_FLUSH_COMMAND", flush_database)(self, database=db)
        self.db_flush_done = True
        self.db_rollback_done = True # flush is stronger than rollback
        self.stack.set_attr_whole_stack('fixtures_loaded', False)

    def _do_rollback(self, test):
        from django.db import transaction
        transaction.rollback()
        transaction.leave_transaction_management()
        self.db_rollback_done = True
        self.stack.set_attr_whole_stack('fixtures_loaded', False)


class DjangoTranslationPlugin(Plugin):
    """
    For testcases with selenium_start set to True, connect to Selenium RC.
    """
    activation_parameter = '--with-djangotranslations'
    name = 'djangotranslations'

    score = 70

    def options(self, parser, env=os.environ): # pylint: disable=W0102
        Plugin.options(self, parser, env)

    def configure(self, options, config):
        Plugin.configure(self, options, config)

    def startTest(self, test):
        # set translation, if allowed
        if getattr_test(test, "make_translations", None):
            from django.conf import settings
            from django.utils import translation
            lang = getattr_test(test, "translation_language_code", None)
            if not lang:
                lang = getattr(settings, "LANGUAGE_CODE", 'en-us')
            translation.activate(lang)

    def stopTest(self, test): # pylint: disable=W0613,R0201
        from django.utils import translation
        translation.deactivate()


class SeleniumPlugin(Plugin):
    """
    For testcases with selenium_start set to True, connect to Selenium RC.
    """
    activation_parameter = '--with-selenium'
    name = 'selenium'

    score = 80

    def options(self, parser, env=os.environ): # pylint: disable=W0102
        Plugin.options(self, parser, env)

    def configure(self, options, config):
        Plugin.configure(self, options, config)

    def beforeTest(self, test):
        # enabling test must be in beforeTest so test can be checked for is_skipped() where is also required_sane_plugin
        # check, so all plugins must be already enabled in startTest
        test_case = get_test_case_class(test)
        enable_test(test_case, 'selenium_plugin_started')

    def startTest(self, test):
        """
        When preparing test, check whether to make our database fresh
        """

        from django.conf import settings
        from django.utils.importlib import import_module

        test_case = get_test_case_class(test)

        # import selenium class to use
        selenium_import = getattr(settings, "DST_SELENIUM_DRIVER",
                            "djangosanetesting.selenium.driver.selenium").split(".")
        selenium_module, selenium_cls = ".".join(selenium_import[:-1]), selenium_import[-1]
        selenium = getattr(import_module(selenium_module), selenium_cls)

        if getattr_test(test, "selenium_start", False):
            browser = getattr(test_case, 'selenium_browser_command', None)
            if browser is None:
                browser = getattr(settings, "SELENIUM_BROWSER_COMMAND", '*opera')

            sel = selenium(
                      getattr(settings, "SELENIUM_HOST", 'localhost'),
                      int(getattr(settings, "SELENIUM_PORT", 4444)),
                      browser,
                      getattr(settings, "SELENIUM_URL_ROOT", get_live_server_path()),
                  )
            try:
                sel.start()
                test_case.selenium_started = True
            except Exception, err: # pylint: disable=W0703
                # we must catch it all as there is untyped socket exception on Windows :-]]]
                if getattr(settings, "FORCE_SELENIUM_TESTS", False):
                    raise
                else:
                    raise SkipTest(err)
            else:
                if isinstance(test.test, nose.case.MethodTestCase):
                    test.test.test.im_self.selenium = sel
                else:
                    raise SkipTest("Selenium test cannot be function-test")

    def stopTest(self, test):
        if getattr_test(test, "selenium_started", False):
            test.test.test.im_self.selenium.stop()
            test.test.test.im_self.selenium = None


class SaneTestSelectionPlugin(Plugin):
    """ Accept additional options, so we can filter out test we don't want """
    RECOGNIZED_TESTS = ["unit", "database", "destructivedatabase", "http", "selenium"]
    score = 150

    def __init__(self):
        super(SaneTestSelectionPlugin, self).__init__()
        self.enabled_tests = None

    def options(self, parser, env=os.environ): # pylint: disable=W0102
        Plugin.options(self, parser, env)
        parser.add_option(
            "-u", "--select-unittests", action="store_true",
            default=False, dest="select_unittests",
            help="Run all unittests"
        )
        parser.add_option(
            "--select-databasetests", action="store_true",
            default=False, dest="select_databasetests",
            help="Run all database tests"
        )
        parser.add_option(
            "--select-destructivedatabasetests", action="store_true",
            default=False, dest="select_destructivedatabasetests",
            help="Run all destructive database tests"
        )
        parser.add_option(
            "--select-httptests", action="store_true",
            default=False, dest="select_httptests",
            help="Run all HTTP tests"
        )
        parser.add_option(
            "--select-seleniumtests", action="store_true",
            default=False, dest="select_seleniumtests",
            help="Run all Selenium tests"
        )

    def configure(self, options, config):
        Plugin.configure(self, options, config)
        self.enabled_tests = [i for i in self.RECOGNIZED_TESTS if getattr(options, "select_%stests" % i, False)]

    def startTest(self, test):
        test_case = get_test_case_class(test)
        if getattr_test(test, "test_type", "unit") not in self.enabled_tests:
            raise SkipTest(u"Test type %s not enabled" % getattr(test_case, "test_type", "unit"))

##########
### Result plugin is used when using Django test runner
### Taken from django-nose project.
### (C) Jeff Balogh and contributors, released under BSD license.
##########

class ResultPlugin(Plugin):
    """
    Captures the TestResult object for later inspection.

    nose doesn't return the full test result object from any of its runner
    methods.  Pass an instance of this plugin to the TestProgram and use
    ``result`` after running the tests to get the TestResult object.
    """

    name = "djangoresult"
    activation_parameter = '--with-djangoresult'
    enabled = True

    def __init__(self):
        super(ResultPlugin, self).__init__()
        self.result = None

    def configure(self, options, config):
        Plugin.configure(self, options, config)

    def finalize(self, result):
        self.result = result
