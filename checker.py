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


"""Module to handle type checking.
"""


from __future__ import print_function

import inspect
import sys
import types
from pytypedecl import pytd
from pytypedecl.parse import utils

_parse_utils = utils.ParserUtils()


def IsFunctionInModule(function, module):
  return inspect.isfunction(function) and inspect.getmodule(function) == module


def Functions(module):
  return ((func.__name__, func) for func in module.__dict__.itervalues()
          if IsFunctionInModule(func, module))


def Classes(module):
  return inspect.getmembers(module, inspect.isclass)


def MethodsForClass(cls):
  return inspect.getmembers(cls, inspect.ismethod)


class CheckTypeAnnotationError(Exception):
  """An exception encapsulating type checking errors.

     A list of error messages is passed to the constructor.
  """
  pass


def ParamTypeErrorMsg(func_name, p_name, actual_p, expected_t):
  return ("[TYPE_ERROR] Function: {f}, parameter: {p}"
          " => FOUND: {found:s} but EXPECTED: {expected:s}").format(
              f=func_name, p=p_name, found=actual_p, expected=expected_t)


def ReturnTypeErrorMsg(func_name, actual_t, expected_t):
  return ("[TYPE_ERROR] Function: {f}, returns {found:s} but "
          "EXPECTED {expected:s}").format(
              f=func_name, found=actual_t, expected=expected_t)


def ExceptionTypeErrorMsg(func_name, actual_e, expected_e):
  return ("[TYPE_ERROR] Function: {f}, raised {found:s} but "
          "EXPECTED one of {expected:s}").format(
              f=func_name, found=actual_e, expected=expected_e)


# TODO(raoulDoc): improve error message (actual args)
def OverloadingTypeErrorMsg(func_name):
  return ("[TYPE_ERROR] Function: {f}, overloading error "
          "no matching signature found").format(f=func_name)


def GeneratorGenericTypeErrorMsg(func_name, gen_to_wrap,
                                 iteration, actual_t, expected_t):
  return ("{} {!r} iteration #{} was a {} not an {}"
          .format(func_name,
                  gen_to_wrap,
                  iteration,
                  actual_t,
                  expected_t))


def _EvalWithModuleContext(expr, module):
  # TODO: use something like library_types/ast.py:_ParseLiteral
  return eval(expr, module.__dict__)


def ConvertToType(module, type_node):
  """Helper for converting a type node to a valid Python type.

  Args:
    module: The module to look up symbols/types
    type_node: A type node to convert into a python type

  Returns:
    A valid Python type. Note that None is considered a type in
    the declaration language, but a value in Python. So a string
    None is converted to a NoneType. We use the module object to look
    up potential type definitions defined inside that module.

  Raises:
    TypeError: if the type node passed is not supported/unknown
  """
  # unknown type can be passed through
  if isinstance(type_node, pytd.UnknownType):
    return type_node
  # clean up str
  if isinstance(type_node, pytd.BasicType):
    if type_node.containing_type == "None":
      return types.NoneType
    elif type_node.containing_type == "generator":
      return types.GeneratorType
    else:
      res = _EvalWithModuleContext(type_node.containing_type, module)
      assert isinstance(res, type), (type_node.containing_type, repr(res))
      return res

  elif isinstance(type_node, pytd.NoneAbleType):
    return pytd.NoneAbleType(ConvertToType(module,
                                           type_node.base_type))

  elif isinstance(type_node, pytd.UnionType):
    return pytd.UnionType([ConvertToType(module, t)
                           for t in type_node.type_list])

  elif isinstance(type_node, pytd.IntersectionType):
    return pytd.IntersectionType([ConvertToType(module, t)
                                  for t in type_node.type_list])

  elif isinstance(type_node, pytd.GenericType1):
    return pytd.GenericType1(ConvertToType(module,
                                           type_node.base_type),
                             ConvertToType(module,
                                           type_node.type1))

  elif isinstance(type_node, pytd.GenericType2):
    return pytd.GenericType2(ConvertToType(module,
                                           type_node.base_type),
                             ConvertToType(module,
                                           type_node.type1),
                             ConvertToType(module,
                                           type_node.type2))
  else:
    raise TypeError("Unknown type of type_node: {!r}".format(type_node))


# functools.wraps doesn't work on generators
def _WrapGenWithTypeCheck(func_name, gen_to_wrap, element_type):
  """Typechecking decorator for typed generators."""
  def _TypeCheckPipeGenerator():
    for iteration, elem in enumerate(gen_to_wrap):
      if not isinstance(elem, element_type):
        error_msg = GeneratorGenericTypeErrorMsg(func_name,
                                                 gen_to_wrap,
                                                 iteration + 1,
                                                 type(elem),
                                                 element_type)
        raise CheckTypeAnnotationError([error_msg])
      yield elem
  return _TypeCheckPipeGenerator()


# see: http://docs.python.org/2/reference/datamodel.html
# we use im_self to differentiate bound vs unbound methods
def _IsClassMethod(func):
  return hasattr(func, "im_self") and func.im_self


def IsCompatibleType(actual, formal):
  """Check compatibility of an expression with a type definition.

  Args:
    actual: an expression being evaluated
    formal: type expected for this expression

  Returns:
    A boolean whether the actual expression is compatible with
    the formal type definition

  Raises:
    TypeError: if a generic type is not supported
  """

  if isinstance(formal, pytd.UnknownType):
    # we don't type check unknown type, let python deal with it
    return True
  if isinstance(formal, pytd.NoneAbleType):
    return (IsCompatibleType(actual, types.NoneType)
            or IsCompatibleType(actual, formal.base_type))
  if isinstance(formal, pytd.UnionType):
    for t in formal.type_list:
      if IsCompatibleType(actual, t):
        return True
    return False
  if isinstance(formal, pytd.IntersectionType):
    for t in formal.type_list:
      if not IsCompatibleType(actual, t):
        return False
    return True
  # check if base type matches
  # then check that all elements match too (e.g. a list[int])
  if isinstance(formal, pytd.GenericType1):
    if isinstance(actual, formal.base_type):
      # we don't consume decorators, rather their elements are
      # typechecked on demand. See _Check function
      if not isinstance(actual, types.GeneratorType):
        return all(
            isinstance(e, formal.type1) for e in actual)
      return True
    return False
  # TODO(raoulDoc): GenericType2, assume only dict for now
  if isinstance(formal, pytd.GenericType2):
    if not isinstance(actual, dict):
      raise TypeError("Only dict is supported for types with 2 type params")
    return all(
        isinstance(k, formal.type1) and isinstance(v, formal.type2)
        for k, v in actual.items())
  # Basic Type
  return isinstance(actual, formal)


def _GetParamTypeErrors(module, func_name, func_sig, args):
  """Helper for checking actual params vs formal params signature.

  Args:
    module: The module to look up symbols/types
    func_name: function name
    func_sig: function definition (Signature)
    args: actual arguments passed to the function

  Returns:
    A list of potential type errors
  """
  params = ((p.name, p.type) for p in func_sig.params)
  param_cmp_types = ((func_name, args[i], ConvertToType(module, t))
                     for i, (func_name, t) in enumerate(params))
  params_type_error_list = [ParamTypeErrorMsg(func_name, n, type(p), t)
                            for n, p, t in param_cmp_types
                            if not IsCompatibleType(p, t)]

  return params_type_error_list


def _GetExceptionsTupleFromFuncSig(module, func_sig):
  """Helper for extracting exceptions from a function definition.

  Args:
      module: The module to look up symbols/types
      func_sig: function definition

  Returns:
      a tuple of exceptions from the function definition
  """
  return tuple(ConvertToType(module, e.containing_type)
               for e in func_sig.exceptions)


def TypeCheck(module, func_name, func, func_sigs):
  """Decorator for typechecking a function.

  Args:
    module: The module associated with the function to typecheck
    func_name: Name of the function that's being checked.
    func: A function to typecheck
    func_sigs: signatures of the function (Function)

  Returns:
    A decorated function with typechecking assertions
  """
  def Wrapped(*args, **kwargs):
    """Typecheck a function given its signature.

    Args:
      *args: Arguments passed to the function
      **kwargs: Key/Value arguments passed to the function

    Returns:
      The result of calling the function decorated with typechecking

    Raises:
      CheckTypeAnnotationError: Type errors were found
    """
    # TODO(raoulDoc): generalise single sig and multiple sig checking
    # to reuse code?
    # at the moment this implementation is convenient because for
    # single signature we stack the errors before raising them
    # for overloading we only have "no matching signature found"
    if len(func_sigs) == 1:
      func_sig = func_sigs[0]
      # need to copy args tuple into list so can modify individual arg
      # specfically we want to replace args with decorated variants
      mod_args = []

      # decorating all typed generators
      cache_of_generators = {}
      for i, actual in enumerate(args):
        # first check actual is a generator
        if isinstance(actual, types.GeneratorType):
          # resolve the param signature at the formal position i
          resolved_type = ConvertToType(module,
                                        func_sig.params[i].type)
          # Was the generator defined as generic-typed?
          # TODO(raoulDoc): formal  may be a union, so need to extract
          # generator signature
          if isinstance(resolved_type, pytd.GenericType1):
            # if yes replace generator with a decorated version
            # we check if we already created a decorated version
            # for cases such as foo(same_gen, same_gen)
            if actual not in cache_of_generators:
              new_gen = _WrapGenWithTypeCheck(func_name,
                                              actual,
                                              resolved_type.type1)
              cache_of_generators[actual] = new_gen
            # get generator from cache
            mod_args.append(cache_of_generators[actual])
          else:
          # here we have an untyped generator
            mod_args.append(actual)
        else:
          mod_args.append(actual)
      # type checking starts here
      # checking params
      type_error_list = _GetParamTypeErrors(module,
                                            func_name,
                                            func_sig,
                                            args)

      exception_tuple = _GetExceptionsTupleFromFuncSig(module,
                                                       func_sig)
      # checking exceptions
      # semantic is "may raise": function doesn't have to throw
      # an exception despite declaring it in its signature
      # we check for excptions caught that were
      # not explicitly declared in the signature
      try:
        # TODO(raoulDoc): get a better understanding of classmethod
        # Is there a way without removing the first argument?
        if _IsClassMethod(func):
          mod_args = mod_args[1:]
        res = func(*mod_args, **kwargs)
      except Exception as e:
        # check if the exception caught was explicitly declared
        if (not isinstance(e, CheckTypeAnnotationError) and
            not IsCompatibleType(e, exception_tuple)):
          type_error_list.append(ExceptionTypeErrorMsg(
              func_name, type(e), exception_tuple))

          raise CheckTypeAnnotationError(type_error_list, e)
        raise  # rethrow exception to preserve program semantics
      else:
        # checking return type
        expected_return_type = ConvertToType(module,
                                             func_sig.return_type)
        if not IsCompatibleType(res, expected_return_type):
          type_error_list.append(ReturnTypeErrorMsg(
              func_name, type(res), expected_return_type))

        if type_error_list:
          raise CheckTypeAnnotationError(type_error_list)

        return res
   # overloading checking
    else:
      # TODO(raoulDoc): overloaded class method support
      # TODO(raoulDoc): support for overloaded typed generators
      param_sig_checked = ((func_sig,
                            _GetParamTypeErrors(module,
                                                func_name,
                                                func_sig,
                                                args))
                           for func_sig in func_sigs)

      # filter parameter signatures that yield no type errors
      func_sig_candidates = [func_sig
                             for (func_sig, type_errors) in param_sig_checked
                             if not type_errors]
      # nothing? this means no good signatures: overloading error
      if not func_sig_candidates:
        raise CheckTypeAnnotationError(
            [OverloadingTypeErrorMsg(func_name)])

      # need to check return type and exceptions
      try:
        res = func(*args, **kwargs)
      except Exception as e:
        # Is the exception caught valid with at least one func sig?

        for func_sig in func_sig_candidates:
          if IsCompatibleType(e, _GetExceptionsTupleFromFuncSig(module,
                                                                func_sig)):
            raise

        raise CheckTypeAnnotationError(
            [OverloadingTypeErrorMsg(func_name)])
      else:
        # Is the return type valid with at least one func sig?
        for func_sig in func_sig_candidates:
          if IsCompatibleType(res,
                              ConvertToType(module,
                                            func_sig.return_type)):
            return res

        raise CheckTypeAnnotationError(
            [OverloadingTypeErrorMsg(func_name)])

  Wrapped.__name__ = func.__name__
  Wrapped.__doc__ = func.__doc__
  Wrapped.__module__ = func.__module__
  return classmethod(Wrapped) if(_IsClassMethod(func)) else Wrapped


# TODO(raoulDoc): attach line number of functions/classes
def _PrintWarning(msg):
  print("(Warning)", msg, "not annotated", file=sys.stderr)


def _Check(module, classes_to_check, functions_to_check):
  """TypeChecks a module.

  Args:
    module: the module to typecheck
    classes_to_check: list of classes_to_check parsed from the type declarations
    functions_to_check: list of functions parsed from the type declarations
  """

  # typecheck functions in module
  for f_name, f_def in Functions(module):
    allowed_signatures = functions_to_check.get(f_name, None)
    if allowed_signatures is not None:
      module.__dict__[f_name] = TypeCheck(module,
                                          f_name,
                                          f_def,
                                          allowed_signatures)
    else:
      _PrintWarning(f_name)

  # typecheck methods in classes
  for c_name, c_def in Classes(module):
    if c_name in classes_to_check:
      class_methods_to_check = {f.name: f.signatures
                                for f in classes_to_check[c_name].methods}

      for f_name, f_def in MethodsForClass(c_def):
        allowed_signatures = class_methods_to_check.get(f_name, None)
        if allowed_signatures is not None:
          setattr(c_def, f_name, TypeCheck(module,
                                           f_name,
                                           f_def,
                                           allowed_signatures))
        else:
          _PrintWarning(c_name + "." + f_name)
    else:
      _PrintWarning(c_name)


def CheckFromFile(module, path):
  by_name = _parse_utils.LoadTypeDeclarationFromFile(path)
  _Check(module, by_name.classes, by_name.funcs)


def CheckFromData(module, data):
  classes, funcs = _parse_utils.LoadTypeDeclaration(data)
  _Check(module, classes, funcs)
