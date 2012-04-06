from nose.tools import assert_equal, assert_raises, assert_true, assert_false # @UnresolvedImport pylint: disable=E0611 
from djangosanetesting.contextstack import ContextStack, ContextInfo

class TestContextStack(object):
    def __init__(self):
        self.test_items = [
            ContextInfo(fixtures=['data1.json', 'data2.json'], no_database_interaction=False, database_flush=True),
            ContextInfo(no_database_interaction=True),
            ContextInfo(fixtures=['data3.json'], no_database_interaction=False, database_flush_at_end=True),
        ]

    def _create_test_stack(self):
        ''' Creates test stack and fill it with self.test_items '''
        stack = ContextStack()
        for item in self.test_items:
            stack.push(item)
        return stack

    def test_top(self):
        stack = self._create_test_stack()
        assert_equal(stack.top(), self.test_items[-1])

    def test_push_pop(self):
        stack = self._create_test_stack()

        item_count = len(self.test_items)
        for i in range(item_count):
            assert_equal(stack.pop(), self.test_items[item_count - i - 1])
        assert_raises(IndexError, stack.pop)

    def test_push_context(self):
        stack = self._create_test_stack()
        class Dummy(object):
            no_database_interaction = True
        stack.push_context(Dummy)
        node = stack.pop()
        assert_equal(node.no_database_interaction, Dummy.no_database_interaction)

    def test_set_attr_whole_stack(self):
        stack = self._create_test_stack()
        stack.set_attr_whole_stack('fixtures_loaded', True)
        for item in stack:
            assert_true(item.fixtures_loaded)

    def test_get_any_attr(self):
        stack = self._create_test_stack()
        results = {
            'no_database_interaction': True,
            'database_flush': True,
            'database_single_transaction': False,
            'database_single_transaction_at_end': False,
            'database_flush_at_end': True,
        }
        for attr_name, value in results.items():
            assert_equal(stack.get_any_attr(attr_name), value)

    def test_get_unloaded_fixtures(self):
        stack = self._create_test_stack()
        assert_equal(stack.get_unloaded_fixtures(), set(['data1.json', 'data2.json', 'data3.json']))
        stack.set_attr_whole_stack('fixtures_loaded', True)
        assert_equal(stack.get_unloaded_fixtures(), set())
        stack.push(ContextInfo(fixtures=['data4.json'], no_database_interaction=False, database_flush_at_end=True),)
        assert_equal(stack.get_unloaded_fixtures(), set(['data4.json']))

    def test_is_transaction(self):
        stack = self._create_test_stack()
        assert_false(stack.is_transaction())
        for i, (assert_func, node) in enumerate((
            (assert_true, ContextInfo(no_database_interaction=False, database_single_transaction_at_end=True)),
            (assert_true, ContextInfo(no_database_interaction=False, database_single_transaction=True)),
            (assert_true, ContextInfo()),
            (assert_false, ContextInfo(database_flush=True)),
            (assert_false, ContextInfo()))):
            stack.push(node)
            assert_func(stack.is_transaction(), msg='is_transaction does not match test result number %s)' % (i + 1))

    def test_is_transaction_empty(self):
        stack = ContextStack()
        assert_false(stack.is_transaction())

    def test_repr(self):
        stack = self._create_test_stack()
        assert_true(len(stack.__repr__()) > 0)


class TestContextInfo(object):
    def test_sanity_check_in_push(self):
        assert_raises(RuntimeError, ContextInfo, no_database_interaction=True, database_flush=True)
        assert_raises(RuntimeError, ContextInfo, database_flush=True, database_single_transaction=True)
        assert_raises(RuntimeError, ContextInfo, database_flush_at_end=True, database_single_transaction_at_end=True)
        assert_raises(RuntimeError, ContextInfo, database_single_transaction=True, database_single_transaction_at_end=True)

