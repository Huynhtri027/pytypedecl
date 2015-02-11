# -*- coding:utf-8; python-indent:2; indent-tabs-mode:nil -*-

# Copyright 2014 Google Inc. All Rights Reserved.
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


"""Extension of collections.namedtuple for use in representing immutable trees.

Example usage:

  class Data(Node("d1", "d2", "d3")):
    pass
  class X(Node("a", "b")):
    pass
  class Y(Node("c", "d")):
    pass
  class XY(Node("x", "y")):
    pass
  data = Data(42, 43, 44)
  x = X(1, [1, 2])
  y = Y([1], {"data": data})
  xy = XY(x, y)

  class Visitor(object):
    def X(self):
      count_x += 1
    def VisitData(self, node):
      return node.Replace(d3=1000)

  new_xy = xy.Visit(Visitor())

The Node "class" differs from namedtuple in the following ways:

1.) More stringent equality test. collections.namedtuple.__eq__ is implicitly
    tuple equality (which makes two tuples equal if all their values are
    recursively equal), but that allows two objects to be the same if they
    happen to have the same field values.
    To avoid this problem, Node adds the check that the two objects' classes are
    equal (this might be too strong, in which case you'd need to use isinstance
    checks).
2.) Visitor interface. See documentation of Visit() below.
3.) Subclassed __str__ function that uses the current class name instead of
    the name of the tuple this class is based on.

See http://bugs.python.org/issue16279 for why it is unlikely for any these
functionalities to be made part of collections.namedtuple.
"""

import collections
import itertools


def Node(*child_names):
  """Create a new Node class.

  You will typically use this when declaring a new class.
  For example:
    class Coordinate(Node("x", "y")):
      pass

  Arguments:
    *child_names: Names of the children of this node.

  Returns:
    A subclass of (named)tuple.
  """

  namedtuple_type = collections.namedtuple("_", child_names)

  class NamedTupleNode(namedtuple_type):
    """A Node class based on namedtuple."""

    def __eq__(self, other):
      """Compare two nodes for equality.

      This will return True if the two underlying tuples are the same *and* the
      two node types match.

      Arguments:
        other: The Node to compare this one with.
      Returns:
        True or False.
      """
      # This comparison blows up if "other" is an old-style class (not an
      # instance). That's fine, because trying to compare a tuple to a class is
      # almost certainly a programming error, and blowing up is better than
      # silently returning False.
      if self is other:
        return True
      elif self.__class__ is other.__class__:
        return tuple.__eq__(self, other)
      else:
        return NotImplemented

    def __ne__(self, other):
      """Compare two nodes for inequality. See __eq__."""
      if self is other:
        return False
      elif self.__class__ is other.__class__:
        return tuple.__ne__(self, other)
      else:
        return NotImplemented

    def __repr__(self):
      """Returns this tuple converted to a string.

      We output this as <classname>(values...). This differs from raw tuple
      output in that we use the class name, not the name of the tuple this
      class extends. Also, Nodes with only one child will be output as
      Name(value), not Name(value,) to match the constructor syntax.

      Returns:
        Representation of this tuple as a string, including the class name.
      """
      if len(self) == 1:
        return "%s(%r)" % (self.__class__.__name__, self[0])
      else:
        return "%s%r" % (self.__class__.__name__, tuple(self))

    # Expose namedtuple._replace as "Replace", so avoid lint warnings
    # and have consistent method names.
    Replace = namedtuple_type._replace  # pylint: disable=no-member,invalid-name

    def Visit(self, visitor, *args, **kwargs):
      """Visitor interface for transforming a tree of nodes to a new tree.

      You can pass a visitor, and callback functions on that visitor will be
      called for all nodes in the tree. Note that nodes are also allowed to
      be stored in lists and as the values of dictionaries, as long as these
      lists/dictionaries are stored in the named fields of the Node class.
      It's possible to overload the Visit function on Nodes, to do your own
      processing.

      Arguments:
        visitor: An instance of a visitor for this tree. For every node type you
          want to transform, this visitor implements a "Visit<Classname>"
          function named after the class of the node this function should
          target. Note that <Classname> is the *actual* class of the node, so
          if you subclass a Node class, visitors for the superclasses will *not*
          be triggered anymore. Also, visitor callbacks are only triggered
          for subclasses of Node.
        *args: Passed to the visitor callback.
        **kwargs: Passed to the visitor callback.

      Returns:
        Transformed version of this node.
      """
      # This function is overwritten below, so that we have the same im_func
      # even though we generate classes here.
      pass  # COV_NF_LINE
    Visit = _VisitNode  # pylint: disable=invalid-name

  return NamedTupleNode


def _VisitNode(node, visitor, *args, **kwargs):
  """Transform a node and all its children using a visitor.

  This will iterate over all children of this node, and also process certain
  things that are not nodes. The latter are either other supported types of
  containers (right now, lists and dictionaries), which will be scanned for
  nodes regardless, or primitive types, which will be return as-is.

  Args:
    node: The node to transform. Either an actual "instance" of Node, or an
          other type of container (lists, dicts) found while scanning a node
          tree, or any other type (which will be returned unmodified).
    visitor: The visitor to apply. If this visitor has a "Visit<Name>" method,
          with <Name> the name of the Node class, a callback will be triggered,
          and the transformed version of this node will be whatever the callback
          returned, or the original node if the callback returned None.  Before
          calling the Visit callback, the following attribute(s) on the Visitor
          class will be populated:
            vistor.old_node: The node before the child nodes were visited.

          Additionally, if the visitor has a "Enter<Name>" method, that method
          will be called on the original node before descending into it. If
          "Enter<Name>" returns False, the visitor will not visit children of
          this node (the result of "Enter<Name>" is otherwise unused; in
          particular it's OK to return None, which will be ignored).
          ["Enter<Name>" is called pre-order; "Visit<Name> and "Leave<Name>" are
          called post-order.]  A counterpart to "Enter<Name>" is "Leave<Name>",
          which is intended for any clean-up that "Enter<Name>" needs (other
          than that, it's redunddant, and could be combined with "Visit<Name>").
    *args: Passed to visitor callbacks.
    **kwargs: Passed to visitor callbacks.
  Returns:
    The transformed Node (which *may* be the original node but could be a new
     node, even if the contents are the same).
  """

  node_class_name = node.__class__.__name__
  if hasattr(node, "Visit") and node.Visit.im_func != _VisitNode:
    # Node with an overloaded Visit() function. It'll do its own processing.
    return node.Visit(visitor, *args, **kwargs)
  elif isinstance(node, tuple):
    enter_function = getattr(visitor, "Enter" + node_class_name, None)
    if enter_function:
      # The visitor wants to be informed that we're descending into this part
      # of the tree.
      status = enter_function(node, *args, **kwargs)
      # Don't descend if Enter<Node> explicitly returns False, but not None,
      # since None is the default return of Python functions.
      if status is False:
        return node
      # Any other value returned from Enter is ignored, so check:
      assert status is None, repr(node_class_name, status)

    new_children = [_VisitNode(child, visitor, *args, **kwargs)
                    for child in node]
    if any(c1 is not c2 for c1, c2 in itertools.izip(new_children, node)):
      # Exact comparison, because classes deriving from tuple (like namedtuple)
      # have different constructor arguments.
      if node.__class__ is tuple:
        new_node = node.__class__(new_children)
      else:
        # Assume this is a namedtuple. Reinitialize with our current old
        # class (because we changed some of the children). The constructor of
        # namedtuple() differs from tuple(), so we have to pass the current
        # tuple using "*".
        new_node = node.__class__(*new_children)
    else:
      # Optimization: if we didn't change any of the children, keep the entire
      # object the same.
      # TODO: Does this actually have any benefit? The test is
      #                  moderately expensive and a new node just copies a few
      #                  pointers (and turns over a bit of memory). Nobody
      #                  should depend on the tree remaining identical (object
      #                  identity) if the visitor makes no changes to any node.
      new_node = node

    visitor.old_node = node
    # Now call the user supplied callback(s), if they exists. Notice we only do
    # this for tuples.
    visit_function = getattr(visitor, "Visit" + node_class_name, False)
    if (getattr(visitor, "implements_all_node_types", False)
        and node_class_name != "tuple"):
      assert visit_function, "Unimplemented visitor: " + node_class_name
    if visit_function:
      new_node = visit_function(new_node, *args, **kwargs)
    leave_function = getattr(visitor, "Leave" + node_class_name, False)
    if leave_function:
      # Clean-up from Enter/Visit
      leave_function(node, *args, **kwargs)

    del visitor.old_node
    return new_node
  elif isinstance(node, list):
    new_list_entries = [_VisitNode(child, visitor, *args, **kwargs)
                        for child in node]
    if any(c1 is not c2 for c1, c2 in zip(new_list_entries, node)):
      # Since some of our children changed, instantiate a new list.
      return node.__class__(new_list_entries)
  elif isinstance(node, dict):
    new_dict = {k: _VisitNode(child, visitor, *args, **kwargs)
                for k, child in node.items()}
    if any(id(new_dict[k]) != id(node[k]) for k in node):
      # Return a new dictionary, but with the current class, in case the user
      # subclasses dict.
      return node.__class__(new_dict)
  return node
