from djangosanetesting.cases import UnitTestCase


class TestScrape(UnitTestCase):
    def test_attributes(self):
        self.assertEqual(self.failureException, AssertionError)
        self.assertTrue(hasattr(self, 'longMessage'))
        self.assertTrue(hasattr(self, 'maxDiff'))
        self.assertEqual(self.countTestCases(), 1)

    def test_assertions(self):
        self.assertEqual(1, 1)
        self.assertNotEqual(1, 2)
        self.assertTrue(True)
        self.assertFalse(False)
        self.assertIs(None, None)
        self.assertIsNot(1, None)
        self.assertIsNone(None)
        self.assertIsNotNone(1)
        self.assertIn(1, (1, 2, 3))
        self.assertNotIn(1, (2, 3))
        self.assertIsInstance(1, int)
        self.assertNotIsInstance(1, float)

        def _raise():
            raise ValueError('Message')
        self.assertRaises(ValueError, _raise)
        self.assertRaisesRegexp(ValueError, 'Mes{2}age', _raise)

        self.assertAlmostEqual(10, 10.001, 2)
        self.assertNotAlmostEqual(10, 11, 2)
        self.assertGreater(2, 1)
        self.assertGreaterEqual(2, 2)
        self.assertLess(1, 2)
        self.assertLessEqual(2, 2)
        self.assertRegexpMatches('some texttext', 'some (text){2}')
        self.assertNotRegexpMatches('a text', 'b+')
        self.assertItemsEqual((1, 2, 3), [1, 2, 3])
        self.assertDictContainsSubset({1: 'a'}, {1: 'a', 2: 'b'})

    def test_clean_up(self):
        # This test is copied from original test for unittest
        # http://hg.python.org/cpython/file/tip/Lib/unittest/test/test_runner.py
        class TestableTest(UnitTestCase):
            def testNothing(self):
                pass

        test = TestableTest('testNothing')
        self.assertEqual(test._cleanups, [])

        cleanups = []

        def cleanup1(*args, **kwargs):
            cleanups.append((1, args, kwargs))

        def cleanup2(*args, **kwargs):
            cleanups.append((2, args, kwargs))

        test.addCleanup(cleanup1, 1, 2, 3, four='hello', five='goodbye')
        test.addCleanup(cleanup2)

        self.assertEqual(test._cleanups,
                         [(cleanup1, (1, 2, 3), dict(four='hello', five='goodbye')), (cleanup2, (), {})])

        self.assertTrue(test.doCleanups())
        self.assertEqual(cleanups, [(2, (), {}), (1, (1, 2, 3), dict(four='hello', five='goodbye'))])
