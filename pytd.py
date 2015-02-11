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

# Our way of using namedtuple is confusing pylint.
# pylint: disable=no-member

"""AST representation of a pytd file."""


import re
from pytypedecl.parse import node


# TODO(ampere): Add __new__ to Type subclasses that contain sequences to
#               convert arguments to tuples?


class TypeDeclUnit(node.Node('constants', 'classes', 'functions', 'modules')):
  """Module node. Holds module contents (classes / functions) and submodules.

  Attributes:
    constants: List of module-level constants.
    functions: List of functions defined in this type decl unit.
    classes: List of classes defined in this type decl unit.
    modules: Map of submodules of the current module.
  """
  __slots__ = ()

  def Lookup(self, name):
    """Convenience function: Look up a given name in the global namespace.

    Tries to find a constant, function or class by this name.

    Args:
      name: Name to look up.

    Returns:
      A Constant, Function or Class.

    Raises:
      KeyError: if this identifier doesn't exist.
    """
    # TODO: Remove. Change constants, classes and functions to dict.
    try:
      return self._name2item[name]
    except AttributeError:
      self._name2item = {}
      for x in self.constants + self.functions + self.classes:
        self._name2item[x.name] = x
      return self._name2item[name]

  def __hash__(self):
    return id(self)

  def __eq__(self, other):
    return id(self) == id(other)

  def __ne__(self, other):
    return id(self) != id(other)


class Constant(node.Node('name', 'type')):
  __slots__ = ()


class Class(node.Node('name', 'parents', 'methods', 'constants', 'template')):
  """Represents a class declaration.

  Used as dict/set key, so all components must be hashable.

  Attributes:
    name: Class name (string)
    parents: The super classes of this class (instances of Type).
    methods: Tuple of class methods (instances of Function).
    constants: Tuple of constant class attributes (instances of Constant).
    template: Tuple of TemplateItem instances.
  """
  # TODO: Rename "parents" to "bases". "Parents" is confusing since we're
  #              in a tree.

  # Override __new__ so that we can catch un-hashable components.
  # TODO: Remove this, once we're sure all callers behave properly
  def __new__(cls, name, parents, methods, constants, template):
    self = super(Class, cls).__new__(cls, name, parents, methods,
                                     constants, template)
    # TODO: remove the following once we're sure that
    #                  caller never passes in None:
    assert isinstance(template, tuple), (type(template), template)
    hash(self)  # Make sure that the args are of sufficiently correct types
    return self

  # Override _replace so that we can catch un-hashable components.
  # TODO: Remove this, once we're sure all callers behave properly
  def _replace(self, **kwargs):
    result = super(Class, self)._replace(**kwargs)  # pylint: disable=invalid-name
    hash(result)  # Make sure that the args are of sufficiently correct types
    return result

  __slots__ = ()

  def Lookup(self, name):
    """Convenience function: Look up a given name in the class namespace.

    Tries to find a method or constant by this name in the class.

    Args:
      name: Name to look up.

    Returns:
      A Constant or Function instance.

    Raises:
      KeyError: if this identifier doesn't exist in this class.
    """
    # TODO: Remove this. Make methods and constants dictionaries.
    try:
      return self._name2item[name]
    except AttributeError:
      self._name2item = {}
      for x in self.methods + self.constants:
        self._name2item[x.name] = x
      return self._name2item[name]


class Function(node.Node('name', 'signatures')):
  """A function or a method.

  Attributes:
    name: The name of this function.
    signatures: Possible list of parameter type combinations for this function.
  """
  __slots__ = ()


class Signature(node.Node('params', 'return_type', 'exceptions', 'template',
                          'has_optional')):
  """Represents an individual signature of a function.

  For overloaded functions, this is one specific combination of parameters.
  For non-overloaded functions, there is a 1:1 correspondence between function
  and signature.

  Attributes:
    name: The name of this function.
    params: The list of parameters for this function definition.
    return_type: The return type of this function.
    exceptions: List of exceptions for this function definition.
    template: names for bindings for bounded types in params/return_type
    has_optional: Do we have optional parameters ("...")?
  """
  __slots__ = ()


class Parameter(node.Node('name', 'type')):
  """Represents a parameter of a function definition.

  Attributes:
    name: The name of the parameter.
    type: The type of the parameter.
  """
  __slots__ = ()


# Conceptually, this is a subtype of Parameter:
class MutableParameter(node.Node('name', 'type', 'new_type')):
  """Represents a parameter that's modified by the function.

  Attributes:
    name: The name of the parameter.
    type: The type of the parameter.
    new_type: The type the parameter will have after the function is called.
  """
  __slots__ = ()


class TypeParameter(node.Node('name')):
  """Represents a type parameter.

  A type parameter is a bound variable in the context of a function or class
  definition. It specifies an equivalence between types.
  For example, this defines a identity function:
    def f<T>(x: T) -> T
  """
  __slots__ = ()


class TemplateItem(node.Node('type_param', 'within_type')):
  """Represents "template name extends bounded_type".

  This is used for classes and signatures. The 'template' field of both is
  a list of TemplateItems. Note that *using* the template happens through
  TypeParameters.  E.g. in:
    class A<T>:
      def f(T x) -> T
  both the "T"s in the definition of f() are using pytd.TypeParameter to refer
  to the TemplateItem in class A's template.

  Attributes:
    type_param: the TypeParameter instance used. This is the actual instance
      that's used wherever this type parameter appears, e.g. within a class.
    within_type: the "extends" type for this name (e.g., NamedType('object'))
  """
  __slots__ = ()

  @property
  def name(self):
    return self.type_param.name


# Types can be:
# 1.) NamedType:
#     Specifies a type by name (i.e., a string)
# 2.) NativeType
#     Points to a Python type. (int, float etc.)
# 3.) ClassType
#     Points back to a Class in the AST. (This makes the AST circular)
# 4.) GenericType
#     Contains a base type and parameters.
# 5.) UnionType / IntersectionType
#     Can be multiple types at once.
# 6.) NothingType / UnknownType
#     Special purpose types that represent nothing or everything.
# 7.) TypeParameter
#     A placeholder for a type.
# 8.) Scalar
#     A singleton type. Not currently used, but supported by the parser.
# For 1-3, the file visitors.py contains tools for converting between the
# corresponding AST representations.


class NamedType(node.Node('name')):
  """A type specified by name."""
  __slots__ = ()

  def __str__(self):
    return str(self.name)


class NativeType(node.Node('python_type')):
  """A type specified by a native Python type. Used during runtime checking."""
  __slots__ = ()


class ClassType(node.Node('name')):
  """A type specified through an existing class node."""

  # This type is different from normal nodes:
  # (a) It's mutable, and there are functions (parse/visitors.py:FillInClasses)
  #     that modify a tree in place.
  # (b) Because it's mutable, it's not actually using the tuple/Node interface
  #     to store things (in particular, the pointer to the existing class).
  # (c) Visitors will not process the "children" of this node. Since we point
  #     to classes that are back at the top of the tree, that would generate
  #     cycles.

  __slots__ = ()

  def __new__(cls, name, clsref=None):
    self = super(ClassType, cls).__new__(cls, name)
    self.cls = clsref  # potentially filled in later (by visitors.FillInClasses)
    return self

  # __eq__ is inherited (using tuple equality + requiring the two classes
  #                      be the same)

  def __str__(self):
    return str(self.cls.name) if self.cls else self.name

  def __repr__(self):
    return '{type}{cls}({name})'.format(
        type=type(self).__name__, name=self.name,
        cls='<unresolved>' if self.cls is None else '')


class UnknownType(node.Node()):
  """A type we know nothing about yet."""
  __slots__ = ()


class NothingType(node.Node()):
  """An "impossible" type, with no instances.

  Also known as the "uninhabited" type. For representing empty lists, and
  functions that never return.
  """
  __slots__ = ()


class Scalar(node.Node('value')):
  __slots__ = ()


class UnionType(node.Node('type_list')):
  """A union type that contains all types in self.type_list."""
  __slots__ = ()

  # NOTE: type_list is kept as a tuple, to preserve the original order
  #       even though in most respects it acts like a frozenset

  def __hash__(self):
    # See __eq__ - order doesn't matter, so use frozenset
    return hash(frozenset(self.type_list))

  def __eq__(self, other):
    if self is other:
      return True
    if isinstance(other, UnionType):
      # equality doesn't care about the ordering of the type_list
      return frozenset(self.type_list) == frozenset(other.type_list)
    return NotImplemented

  def __ne__(self, other):
    return not self == other


# TODO: Do we still need this?
class IntersectionType(node.Node('type_list')):
  __slots__ = ()


class GenericType(node.Node('base_type', 'parameters')):
  """Generic type. Takes a base type and type paramters.

  This corresponds to the syntax: type<type1,>, type<type1, type2> (etc.).

  Attributes:
    base_type: The base type. Instance of Type.
    parameters: Type paramters. Tuple of instances of Type.
  """
  __slots__ = ()


class HomogeneousContainerType(GenericType):
  """Special generic type for homogeneous containers. Only has one type param.

  This differs from GenericType in that it assumes *all* items in a container
  will be the same type. The syntax is type<t>. (Vs type<t,> for GenericType.)
  """
  __slots__ = ()

  @property
  def element_type(self):
    return self.parameters[0]


# So we can do "isinstance(node, pytd.TYPE)":
TYPE = (NamedType, NativeType, ClassType, UnknownType, UnionType,
        NothingType, GenericType, TypeParameter, Scalar,
        IntersectionType, Scalar)


def Print(n):
  """Convert a PYTD node to a string."""
  # TODO: fix circular import
  from pytypedecl.parse import visitors
  res = n.Visit(visitors.PrintVisitor())
  # Remove trailing blanks on lines (*not* \s which includes \n) -- these come
  # from indents that have no other code on them.
  return re.sub(r" +\n", "\n", res)


def PrologConstraints(n, prefix):
  """Convert a PYTD node to a Prolog constraint string.

  Args:
    n: the pytd tree (node)
    prefix: the prefix to add to each clause.

  Returns:
    string of constraint clauses.
  """

  # TODO: fix circular import
  from pytypedecl.parse import visitors
  return  n.Visit(visitors.PrologConstraintsVisitor(prefix))
