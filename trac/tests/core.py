# -*- coding: utf-8 -*-
#
# Copyright (C) 2005-2009 Edgewall Software
# Copyright (C) 2005 Christopher Lenz <cmlenz@gmx.de>
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at http://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at http://trac.edgewall.org/log/.
#
# Author: Christopher Lenz <cmlenz@gmx.de>

import trac.tests.compat
from trac.core import *
from trac.core import ComponentManager

import unittest


class TracErrorTestCase(unittest.TestCase):

    def test_init(self):
        e = TracError("the message", "the title", True)
        self.assertEqual("the message", e.message)
        self.assertEqual("the title", e.title)
        self.assertEqual(True, e.show_traceback)

    def test_unicode(self):
        e = TracError("the message")
        self.assertEqual("the message", unicode(e))


class ITest(Interface):
    def test():
        """Dummy function."""


class IOtherTest(Interface):
    def other_test():
        """Other dummy function."""


class ComponentTestCase(unittest.TestCase):

    def setUp(self):
        from trac.core import ComponentMeta
        self.compmgr = ComponentManager()

        # Make sure we have no external components hanging around in the
        # component registry
        self.old_registry = ComponentMeta._registry
        ComponentMeta._registry = {}

    def tearDown(self):
        # Restore the original component registry
        from trac.core import ComponentMeta
        ComponentMeta._registry = self.old_registry

    def test_base_class_not_registered(self):
        """
        Make sure that the Component base class does not appear in the component
        registry.
        """
        from trac.core import ComponentMeta
        self.assertNotIn(Component, ComponentMeta._components)
        self.assertRaises(TracError, self.compmgr.__getitem__, Component)

    def test_abstract_component_not_registered(self):
        """
        Make sure that a Component class marked as abstract does not appear in
        the component registry.
        """
        from trac.core import ComponentMeta
        class AbstractComponent(Component):
            abstract = True
        self.assertNotIn(AbstractComponent, ComponentMeta._components)
        self.assertRaises(TracError, self.compmgr.__getitem__,
                          AbstractComponent)

    def test_unregistered_component(self):
        """
        Make sure the component manager refuses to manage classes not derived
        from `Component`.
        """
        class NoComponent(object):
            pass
        self.assertRaises(TracError, self.compmgr.__getitem__, NoComponent)

    def test_component_registration(self):
        """
        Verify that classes derived from `Component` are managed by the
        component manager.
        """
        class ComponentA(Component):
            pass
        self.assertTrue(self.compmgr[ComponentA])
        self.assertTrue(ComponentA(self.compmgr))

    def test_component_identity(self):
        """
        Make sure instantiating a component multiple times just returns the
        same instance again.
        """
        class ComponentA(Component):
            pass
        c1 = ComponentA(self.compmgr)
        c2 = ComponentA(self.compmgr)
        self.assertIs(c1, c2, 'Expected same component instance')
        c2 = self.compmgr[ComponentA]
        self.assertIs(c1, c2, 'Expected same component instance')

    def test_component_initializer(self):
        """
        Makes sure that a components' `__init__` method gets called.
        """
        class ComponentA(Component):
            def __init__(self):
                self.data = 'test'
        self.assertEqual('test', ComponentA(self.compmgr).data)
        ComponentA(self.compmgr).data = 'newtest'
        self.assertEqual('newtest', ComponentA(self.compmgr).data)

    def test_inherited_component_initializer(self):
        """
        Makes sure that a the `__init__` method of a components' super-class
        gets called if the component doesn't override it.
        """
        class ComponentA(Component):
            def __init__(self):
                self.data = 'foo'
        class ComponentB(ComponentA):
            def __init__(self):
                self.data = 'bar'
        class ComponentC(ComponentB):
            pass
        self.assertEqual('bar', ComponentC(self.compmgr).data)
        ComponentC(self.compmgr).data = 'baz'
        self.assertEqual('baz', ComponentC(self.compmgr).data)

    def test_implements_called_outside_classdef(self):
        """
        Verify that calling implements() outside a class definition raises an
        `AssertionError`.
        """
        try:
            implements()
        except AssertionError:
            pass
        else:
            self.fail('Expected AssertionError')

    def test_implements_multiple(self):
        """
        Verify that a component "implementing" an interface more than once
        (e.g. through inheritance) is not called more than once from an
        extension point.
        """
        log = []
        class Parent(Component):
            abstract = True
            implements(ITest)
        class Child(Parent):
            implements(ITest)
            def test(self):
                log.append("call")
        class Other(Component):
            tests = ExtensionPoint(ITest)
        for test in Other(self.compmgr).tests:
            test.test()
        self.assertEqual(["call"], log)

    def test_attribute_access(self):
        """
        Verify that accessing undefined attributes on components raises an
        `AttributeError`.
        """
        class ComponentA(Component):
            pass
        comp = ComponentA(self.compmgr)
        try:
            comp.foo
            self.fail('Expected AttributeError')
        except AttributeError:
            pass

    def test_nonconforming_extender(self):
        """
        Verify that accessing a method of a declared extension point interface
        raises a normal `AttributeError` if the component does not implement
        the method.
        """
        class ComponentA(Component):
            tests = ExtensionPoint(ITest)
        class ComponentB(Component):
            implements(ITest)
        tests = iter(ComponentA(self.compmgr).tests)
        try:
            tests.next().test()
            self.fail('Expected AttributeError')
        except AttributeError:
            pass

    def test_extension_point_with_no_extension(self):
        """
        Verify that accessing an extension point with no extenders returns an
        empty list.
        """
        class ComponentA(Component):
            tests = ExtensionPoint(ITest)
        tests = iter(ComponentA(self.compmgr).tests)
        self.assertRaises(StopIteration, tests.next)

    def test_extension_point_with_one_extension(self):
        """
        Verify that a single component extending an extension point can be
        accessed through the extension point attribute of the declaring
        component.
        """
        class ComponentA(Component):
            tests = ExtensionPoint(ITest)
        class ComponentB(Component):
            implements(ITest)
            def test(self):
                return 'x'
        tests = iter(ComponentA(self.compmgr).tests)
        self.assertEqual('x', tests.next().test())
        self.assertRaises(StopIteration, tests.next)

    def test_extension_point_with_two_extensions(self):
        """
        Verify that two components extending an extension point can be accessed
        through the extension point attribute of the declaring component.
        """
        class ComponentA(Component):
            tests = ExtensionPoint(ITest)
        class ComponentB(Component):
            implements(ITest)
            def test(self):
                return 'x'
        class ComponentC(Component):
            implements(ITest)
            def test(self):
                return 'y'
        results = [test.test() for test in ComponentA(self.compmgr).tests]
        self.assertEqual(['x', 'y'], sorted(results))

    def test_inherited_extension_point(self):
        """
        Verify that extension points are inherited to sub-classes.
        """
        class BaseComponent(Component):
            tests = ExtensionPoint(ITest)
        class ConcreteComponent(BaseComponent):
            pass
        class ExtendingComponent(Component):
            implements(ITest)
            def test(self):
                return 'x'
        tests = iter(ConcreteComponent(self.compmgr).tests)
        self.assertEqual('x', tests.next().test())
        self.assertRaises(StopIteration, tests.next)

    def test_inherited_implements(self):
        """
        Verify that a component with a super-class implementing an extension
        point interface is also registered as implementing that interface.
        """
        class BaseComponent(Component):
            implements(ITest)
            abstract = True
        class ConcreteComponent(BaseComponent):
            pass
        from trac.core import ComponentMeta
        self.assertIn(ConcreteComponent, ComponentMeta._registry.get(ITest, []))

    def test_inherited_implements_multilevel(self):
        """
        Verify that extension point interfaces are inherited for more than
        one level of inheritance.
        """
        class BaseComponent(Component):
            implements(ITest)
            abstract = True
        class ChildComponent(BaseComponent):
            implements(IOtherTest)
            abstract = True
        class ConcreteComponent(ChildComponent):
            pass
        from trac.core import ComponentMeta
        self.assertIn(ConcreteComponent, ComponentMeta._registry.get(ITest, []))
        self.assertIn(ConcreteComponent, ComponentMeta._registry.get(IOtherTest, []))

    def test_component_manager_component(self):
        """
        Verify that a component manager can itself be a component with its own
        extension points.
        """
        class ManagerComponent(ComponentManager, Component):
            tests = ExtensionPoint(ITest)
            def __init__(self, foo, bar):
                ComponentManager.__init__(self)
                self.foo, self.bar = foo, bar
        class Extender(Component):
            implements(ITest)
            def test(self):
                return 'x'
        mgr = ManagerComponent('Test', 42)
        self.assertEqual(id(mgr), id(mgr[ManagerComponent]))
        tests = iter(mgr.tests)
        self.assertEqual('x', tests.next().test())
        self.assertRaises(StopIteration, tests.next)

    def test_component_manager_component_isolation(self):
        """
        Verify that a component manager that is also a component will only
        be listed in extension points for components instantiated in
        its scope.

        See bh:comment:5:ticket:438 and #11121
        """
        class ManagerComponentA(ComponentManager, Component):
            implements(ITest)
            def test(self):
                pass

        class ManagerComponentB(ManagerComponentA):
            pass

        class Tester(Component):
            tests = ExtensionPoint(ITest)

        mgrA = ManagerComponentA()
        mgrB = ManagerComponentB()

        self.assertEqual([mgrA], Tester(mgrA).tests)
        self.assertEqual([mgrB], Tester(mgrB).tests)

    def test_instantiation_doesnt_enable(self):
        """
        Make sure that a component disabled by the ComponentManager is not
        implicitly enabled by instantiating it directly.
        """
        class DisablingComponentManager(ComponentManager):
            def is_component_enabled(self, cls):
                return False
        class ComponentA(Component):
            pass
        mgr = DisablingComponentManager()
        instance = ComponentA(mgr)
        self.assertIsNone(mgr[ComponentA])

    def test_invalid_argument_raises(self):
        """
        AssertionError is raised when first argument to initializer is not a
        ComponentManager instance.
        """
        class ComponentA(Component):
            pass
        self.assertRaises(AssertionError, Component)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TracErrorTestCase))
    suite.addTest(unittest.makeSuite(ComponentTestCase))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='suite')
