"""
NoseContextStack to hande important information while nosetests traverses (DFS) through 
packages, modules, test_cases classess, test methods and test functions.
"""

class ContextInfo(object):
    """ Information about one node in traversed tree """
    def __init__(self, fixtures=None, no_database_interaction=None,
                 database_single_transaction=None, database_flush=None,
                 database_single_transaction_at_end=None, database_flush_at_end=None):
        super(ContextInfo, self).__init__()
        self.fixtures = fixtures # list of fixtures
        self.fixtures_loaded = False # flag - fixtures are loaded in test db?
        self.no_database_interaction = no_database_interaction
        self.database_single_transaction = database_single_transaction
        self.database_flush = database_flush
        self.database_single_transaction_at_end = database_single_transaction_at_end
        self.database_flush_at_end = database_flush_at_end

        # Sanity check:
        if self.no_database_interaction:
            for attr_name in ['fixtures', 'database_single_transaction', 'database_flush',
                              'database_single_transaction_at_end', 'database_flush_at_end']:
                if getattr(self, attr_name):
                    raise RuntimeError('You cannot have "%s" without database' % attr_name)
        if self.database_flush:
            for attr_name in ['database_single_transaction', 'database_flush_at_end', 'database_single_transaction_at_end']:
                if getattr(self, attr_name):
                    raise RuntimeError('Having "database_flush" and "%s" does not make sence.' % attr_name)
        if self.database_flush_at_end and self.database_single_transaction_at_end:
            raise RuntimeError('Having "database_flush_at_end" and "database_single_transaction_at_end" does not make sence.')
        if self.database_single_transaction and self.database_single_transaction_at_end:
            raise RuntimeError('Having "database_single_transactoin_at_end" and "database_single_transaction" does not make sence.')


    def __repr__(self):
        return '<nodeinfo %s, %s, %s, %s, %s, %s, %s>' % (self.fixtures, self.fixtures_loaded, self.no_database_interaction,
                                                          self.database_single_transaction, self.database_flush,
                                                          self.database_single_transaction_at_end, self.database_flush_at_end)


class ContextStack(list):
    def __init__(self):
        super(ContextStack, self).__init__()


    def push(self, node):
        self.append(node)

    def push_context(self, nose_context):
        ''' Get NodeInfo object from nose context, push it to stack and return it as return value '''
        node = ContextInfo(
            fixtures=getattr(nose_context, 'fixtures', None),
            no_database_interaction=getattr(nose_context, 'no_database_interaction', None),
            database_single_transaction=getattr(nose_context, 'database_single_transaction', None),
            database_flush=getattr(nose_context, 'database_flush', None),
            database_single_transaction_at_end=getattr(nose_context, 'database_single_transaction_at_end', None),
            database_flush_at_end=getattr(nose_context, 'database_flush_at_end', None)
        )
        self.push(node)
        return node

    def top(self):
        return self[-1]

    def set_attr_whole_stack(self, attr, value):
        ''' Sets attribute attr to value for all nodes in the stack '''
        for node in self:
            setattr(node, attr, value)

    def get_any_attr(self, attr):
        ''' Search the whole stack for attr, returns True if any of the nodes has attr == True '''
        for node in self:
            if getattr(node, attr, None):
                return True
        return False

    def get_unloaded_fixtures(self):
        ''' Return set of all fixtures, which are not loaded (so not including items with fixtures_loaded == True) '''
        return set([fixture
                    for context in self if not context.fixtures_loaded and context.fixtures
                    for fixture in context.fixtures])

    def is_transaction(self):
        ''' Returns whether current state should be in transaction (this is used to check, whether transaction 
            should be started and whether the commit=False should be used for fixtures. (of course first priority have
            test mathod/function attributes, only if unspecified there, this stack method is used).
        '''
        for node in reversed(self):
            if node.database_single_transaction or node.database_single_transaction_at_end:
                return True
            elif node.database_flush or node.database_flush_at_end:
                # flush is stronger than transaction so we don't care what is deeper in the stack anymore:
                return False
        return False
