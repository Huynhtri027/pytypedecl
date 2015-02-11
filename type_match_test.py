# -*- coding:utf-8; python-indent:2; indent-tabs-mode:nil -*-
# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for type_match.py."""

import textwrap
import unittest


from pytypedecl import booleq
from pytypedecl import pytd
from pytypedecl import type_match
from pytypedecl.parse import parser
from pytypedecl.parse import visitors


class TestTypeMatch(unittest.TestCase):
  """Test algorithms and datastructures of booleq.py."""

  def testUnknown(self):
    m = type_match.TypeMatch({})
    eq = m.match_type_against_type(pytd.AnythingType(), pytd.AnythingType(), {})
    self.assertEquals(eq, booleq.TRUE)

  def testNothing(self):
    m = type_match.TypeMatch({})
    eq = m.match_type_against_type(pytd.NothingType(),
                                   pytd.NamedType("A"), {})
    self.assertEquals(eq, booleq.FALSE)

  def testNamed(self):
    m = type_match.TypeMatch({})
    eq = m.match_type_against_type(pytd.NamedType("A"), pytd.NamedType("A"), {})
    self.assertEquals(eq, booleq.TRUE)
    eq = m.match_type_against_type(pytd.NamedType("A"), pytd.NamedType("B"), {})
    self.assertNotEquals(eq, booleq.TRUE)

  def testNamedAgainstGeneric(self):
    m = type_match.TypeMatch({})
    eq = m.match_type_against_type(pytd.GenericType(pytd.NamedType("A"), []),
                                   pytd.NamedType("A"), {})
    self.assertEquals(eq, booleq.TRUE)

  def testFunction(self):
    ast = parser.parse_string(textwrap.dedent("""
      def left(a: int) -> int
      def right(a: int) -> int
    """))
    m = type_match.TypeMatch()
    self.assertEquals(m.match(ast.Lookup("left"), ast.Lookup("right"), {}),
                      booleq.TRUE)

  def testReturn(self):
    ast = parser.parse_string(textwrap.dedent("""
      def left(a: int) -> float
      def right(a: int) -> int
    """))
    m = type_match.TypeMatch()
    self.assertNotEquals(m.match(ast.Lookup("left"), ast.Lookup("right"), {}),
                         booleq.TRUE)

  def testOptional(self):
    ast = parser.parse_string(textwrap.dedent("""
      def left(a: int) -> int
      def right(a: int, ...) -> int
    """))
    m = type_match.TypeMatch()
    self.assertEquals(m.match(ast.Lookup("left"), ast.Lookup("right"), {}),
                      booleq.TRUE)

  def testGeneric(self):
    ast = parser.parse_string(textwrap.dedent("""
      class A<T extends nothing>(nothing):
        pass
      left: A<?>
      right: A<?>
    """))
    ast = visitors.LookupClasses(ast)
    m = type_match.TypeMatch()
    self.assertEquals(m.match_type_against_type(
        ast.Lookup("left").type,
        ast.Lookup("right").type, {}), booleq.TRUE)

  def testClassMatch(self):
    ast = parser.parse_string(textwrap.dedent("""
      class Left(nothing):
        def method(self) -> ?
      class Right(nothing):
        def method(self) -> ?
        def method2(self) -> ?
    """))
    ast = visitors.LookupClasses(ast)
    m = type_match.TypeMatch()
    left, right = ast.Lookup("Left"), ast.Lookup("Right")
    self.assertEquals(m.match(left, right, {}), booleq.TRUE)
    self.assertNotEquals(m.match(right, left, {}), booleq.TRUE)

  def testSubclasses(self):
    ast = parser.parse_string(textwrap.dedent("""
      class A(nothing):
        pass
      class B(A):
        pass
      a : A
      def left(a: B) -> B
      def right(a: A) -> A
    """))
    ast = visitors.LookupClasses(ast)
    m = type_match.TypeMatch({ast.Lookup("a").type: [ast.Lookup("B")]})
    left, right = ast.Lookup("left"), ast.Lookup("right")
    self.assertEquals(m.match(left, right, {}), booleq.TRUE)
    self.assertNotEquals(m.match(right, left, {}), booleq.TRUE)


if __name__ == "__main__":
  unittest.main()
